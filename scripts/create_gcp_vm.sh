#!/bin/bash

# Dừng script nếu có lỗi xảy ra
set -e

# ==========================================
# CẤU HÌNH BIẾN (Sửa lại cho đúng với dự án của bạn)
# ==========================================
PROJECT_ID="your-gcp-project-id"   # Thay bằng Project ID của bạn trên GCP
ZONE="asia-southeast1-b"           # Vùng đặt Server (Singapore)
VM_NAME="needwise-server"          # Tên máy ảo
MACHINE_TYPE="e2-high"           # Cấu hình: e2-medium (2 vCPU, 4GB RAM)
IMAGE_FAMILY="ubuntu-2204-lts"     # Hệ điều hành Ubuntu 22.04 LTS
IMAGE_PROJECT="ubuntu-os-cloud"    # Nguồn cấp OS
DISK_SIZE="30GB"                   # Dung lượng ổ cứng

# Khởi tạo GCP project
echo "🔄 Đang thiết lập project: $PROJECT_ID"
gcloud config set project $PROJECT_ID
gcloud config set compute/zone $ZONE

# ==========================================
# 1. TẠO TƯỜNG LỬA (FIREWALL) CHO HTTP & HTTPS
# ==========================================
echo "🛡️ Đang cấu hình tường lửa mở port 80 và 443..."
# Ghi đè nếu đã tồn tại (dùng --quiet để bỏ qua xác nhận)
gcloud compute firewall-rules create allow-http-https \
    --action=ALLOW \
    --rules=tcp:80,tcp:443 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=http-server,https-server \
    --quiet || echo "⚠️ Firewall rule đã tồn tại, tiếp tục..."

# ==========================================
# 2. TẠO MÁY ẢO KÈM SCRIPT CÀI ĐẶT TỰ ĐỘNG
# ==========================================
echo "🚀 Đang khởi tạo máy ảo Compute Engine: $VM_NAME ($MACHINE_TYPE)..."

# Script khởi động tự động cài Docker và Git khi tạo xong VM
cat << 'EOF' > startup.sh
#!/bin/bash
# Cập nhật và cài đặt các dependencies
apt-get update
apt-get install -y apt-transport-https ca-certificates curl software-properties-common git

# Cài đặt Docker & Docker Compose
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -
add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Cấp quyền docker cho user ubuntu
usermod -aG docker ubuntu
systemctl enable docker
systemctl restart docker
EOF

gcloud compute instances create $VM_NAME \
    --machine-type=$MACHINE_TYPE \
    --image-family=$IMAGE_FAMILY \
    --image-project=$IMAGE_PROJECT \
    --boot-disk-size=$DISK_SIZE \
    --boot-disk-type=pd-balanced \
    --tags=http-server,https-server \
    --metadata-from-file startup-script=startup.sh \
    --quiet

# Xoá file script tạm
rm startup.sh

# ==========================================
# 3. KẾT QUẢ ĐẦU RA
# ==========================================
echo "✅ HOÀN TẤT! Máy ảo của bạn đã được tạo thành công."
echo "🌐 Đang lấy địa chỉ IP Public..."

PUBLIC_IP=$(gcloud compute instances describe $VM_NAME --format='get(networkInterfaces[0].accessConfigs[0].natIP)')

echo "=========================================="
echo "🎯 ĐỊA CHỈ IP PUBLIC: $PUBLIC_IP"
echo "=========================================="
echo "💡 BƯỚC TIẾP THEO:"
echo "1. Đừng quên trỏ tên miền của bạn (A Record) về IP: $PUBLIC_IP"
echo "2. Chờ khoảng 1-2 phút để VM chạy xong script cài đặt Docker."
echo "3. Để truy cập SSH vào máy ảo, chạy lệnh:"
echo "   gcloud compute ssh ubuntu@$VM_NAME --zone=$ZONE"
echo "=========================================="
