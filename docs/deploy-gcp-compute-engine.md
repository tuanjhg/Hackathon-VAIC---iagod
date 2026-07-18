# Triển khai NeedWise lên Google Compute Engine

## 1. Quyết định tài nguyên

Ứng dụng chạy 4 container: Caddy, Next.js 15, FastAPI và PostgreSQL 16 + pgvector. LLM được
gọi qua OpenRouter, không chạy inference trên VM, nên không cần GPU.

| Môi trường | Machine type | Disk | Khi nào dùng |
|---|---:|---:|---|
| Dev/demo rất ít tải | `e2-medium` (2 shared vCPU, 4 GB) | 30 GB | Chỉ demo ngắn; dễ thiếu RAM khi migration/build index |
| Pilot đề xuất | `e2-standard-2` (2 vCPU, 8 GB) | 50 GB `pd-balanced` | 4 container, catalog hiện tại ~30 MB, tải thấp/vừa |
| Production nhỏ | `e2-standard-4` (4 vCPU, 16 GB) | 100 GB | Nhiều request đồng thời hoặc index/catalog tăng |

Chọn Singapore `asia-southeast1` để gần người dùng Việt Nam. Một VM là phương án đơn giản,
chi phí thấp nhưng PostgreSQL và app cùng một failure domain. Đây không phải HA. Khi cần SLA,
backup point-in-time hoặc scale ngang, chuyển PostgreSQL sang Cloud SQL for PostgreSQL có
pgvector, rồi chạy app trên Managed Instance Group hoặc Cloud Run. Không dùng Spot VM vì app
và database đều stateful.

Disk 50 GB bao gồm OS, Docker images, log và database. Thiết lập cảnh báo ở 70/85%, snapshot
hằng ngày và retention ít nhất 7 ngày trước khi coi là production. Container database không
publish port 5432; chỉ 80/443 public. SSH chỉ đi qua IAP.

## 2. Chuẩn bị local

Yêu cầu: Google Cloud SDK (`gcloud`), Docker, Git; tài khoản có quyền tạo Compute, IAM,
Artifact Registry, Secret Manager và Workload Identity Pool. Billing phải được bật cho project.

```bash
gcloud auth login
gcloud auth application-default login
gcloud components update
cp scripts/gcp/config.example.env scripts/gcp/config.env
```

Sửa toàn bộ giá trị trong `config.env`, đặc biệt `PROJECT_ID`, `DOMAIN_NAME` và
`GITHUB_REPOSITORY`. Script mặc định dùng `asia-southeast1-b`; kiểm tra quota/availability bằng:

```bash
gcloud compute machine-types describe e2-standard-2 --zone asia-southeast1-b
gcloud compute project-info describe --project YOUR_PROJECT_ID
```

## 3. Provision hạ tầng bằng SDK local

```bash
chmod +x scripts/create_gcp_vm.sh scripts/gcp/*.sh
./scripts/gcp/01-provision.sh
```

Script idempotent sẽ bật API, tạo Artifact Registry, runtime service account, static IP,
firewall 80/443, firewall IAP SSH, VM Ubuntu 24.04 Shielded VM và cài Docker Compose. Trỏ DNS
A record của domain về static IP được in ra, rồi kiểm tra bootstrap:

```bash
gcloud compute ssh needwise-prod --zone asia-southeast1-b \
  --tunnel-through-iap --command 'sudo test -f /var/log/needwise-startup-complete'
```

## 4. Tạo secret production

```bash
cp deploy/prod.env.example /tmp/needwise-prod.env
chmod 600 /tmp/needwise-prod.env
# Sửa domain, password ngẫu nhiên và LLM key trong file /tmp.
./scripts/gcp/02-put-secret.sh /tmp/needwise-prod.env
```

Mỗi lần chạy tạo version mới, không ghi secret vào GitHub hay image. Không đổi
`POSTGRES_PASSWORD` tùy tiện sau khi volume DB đã được khởi tạo: image PostgreSQL chỉ áp dụng
biến này lần đầu tạo data directory. Password có ký tự đặc biệt phải URL-encode trong hai DSN.
Nếu cần rotate, đổi password trong PostgreSQL trước rồi mới thêm secret version.

## 5. Deploy lần đầu từ local

Sau khi DNS đã trỏ đúng (Caddy cần domain hợp lệ để cấp TLS):

```bash
./scripts/gcp/03-deploy-local.sh
curl -fsS https://YOUR_DOMAIN/api/v1/health
```

Script build hai image với Git SHA, push Artifact Registry, copy manifest qua IAP, pull image,
chạy Alembic/seed/policy index và đợi health check. PostgreSQL dùng named volume nên rollout
không xóa dữ liệu.

Kiểm tra/chẩn đoán:

```bash
gcloud compute ssh needwise-prod --zone asia-southeast1-b --tunnel-through-iap
sudo docker compose -f /opt/needwise/docker-compose.prod.yml --env-file /opt/needwise/.env ps
sudo docker compose -f /opt/needwise/docker-compose.prod.yml --env-file /opt/needwise/.env logs --tail=200 api
```

Rollback dùng tag Git SHA trước đó (image là immutable):

```bash
./scripts/gcp/03-deploy-local.sh PREVIOUS_FULL_OR_SHORT_SHA_TAG
```

Lệnh trên sẽ build lại nếu chạy local. Để rollback không build, SSH và chạy
`remote-deploy.sh` với tag cũ còn trong Artifact Registry. Migration database chỉ được viết
backward-compatible; nếu migration phá vỡ schema thì rollback image không đủ.

## 6. GitHub Actions không dùng service-account key

Từ local chạy một lần:

```bash
./scripts/gcp/04-setup-github-wif.sh
```

Copy các giá trị script in ra vào GitHub repository **Variables**. Tạo GitHub Environment tên
`production`; nên bật required reviewer. Không cần tạo `VM_HOST`, private SSH key hoặc JSON key.
Workflow `.github/workflows/deploy.yml` sẽ test API/web, xác thực bằng GitHub OIDC + Workload
Identity Federation, build/push image theo commit SHA và rollout qua IAP. Chỉ repo đã cấu hình
được impersonate deploy service account.

## 7. Vận hành và giới hạn

- Tạo Monitoring alert cho CPU > 80%, memory > 80%, disk > 70%, uptime check `/api/v1/health`.
- Bật Ops Agent nếu cần memory/disk metrics; các metric này không có đầy đủ từ hypervisor.
- Tạo snapshot schedule cho boot disk. Trước migration lớn, chạy `pg_dump` sang Cloud Storage.
- Pin image theo digest nếu cần supply-chain chặt hơn; hiện deploy theo immutable commit SHA.
- Caddy tự gia hạn HTTPS. Không dùng `DOMAIN_NAME=localhost` trên production.
- Nếu chưa có domain và truy cập trực tiếp bằng public IP, đặt `DOMAIN_NAME=<STATIC_IP>` và
  `SITE_SCHEME=http`; TLS tin cậy cần một DNS name thật trỏ về IP.
- `e2-standard-2` không phải cam kết tải. Sau 1–2 tuần, right-size theo CPU p95, RAM p95,
  database size/IOPS và latency p95; nâng VM cần stop/start ngắn.

Ước tính giá nên lấy trực tiếp bằng Google Cloud Pricing Calculator vì giá theo region, disk,
egress, thuế và discount thay đổi. Các thành phần cần nhập: 730 giờ E2 VM/tháng, 50 GB
pd-balanced, static IPv4 đang sử dụng, Artifact Registry storage, snapshot và internet egress.
