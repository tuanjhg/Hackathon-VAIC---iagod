# Benchmark gate Phase 0

4 việc "PHẢI benchmark ở Phase 0" — bảng cuối `docs/research/dmx-tech-decisions.md`. Mỗi gate ra một quyết định treo (model, flag, CPU/GPU, fallback version), không phải một feature.

**Không chạy được trong sandbox này** — cả 4 script cần một vLLM OpenAI-compatible endpoint thật (self-host trên H100, xem `docs/research/dmx-phan-tich-ke-hoach-2026-07-17.md` §5b). Script đã viết sẵn, sẵn sàng chạy khi cửa sổ GPU (W1 · Phase 0 · 1.0h) mở.

## Chạy

```bash
export VLLM_BASE_URL=http://<host>:8001/v1   # mặc định http://localhost:8001/v1
export VLLM_MODEL=qwen3-32b-fp8              # đúng tên model đã load trong vLLM

python3 scripts/bench/gate1_s2_latency.py          # p95 S2 <700ms?
python3 scripts/bench/gate2_vllm_flags.py --label flags-off   # chạy trước khi bật flag
python3 scripts/bench/gate2_vllm_flags.py --label flags-on    # chạy lại sau khi bật prefix-caching+chunked-prefill
diff scripts/bench/results/gate2_flags-off.json scripts/bench/results/gate2_flags-on.json

pip install -r scripts/bench/requirements-bench.txt
python3 scripts/bench/gate3_embedding_latency.py   # p95 embedding CPU <30ms/query?
python3 scripts/bench/gate4_qwen3_clean_run.py     # 10/10 call sạch (guided_json + hermes tool)?
```

Hoặc `make bench-gates` (gate1+3+4; gate2 chạy tay 2 lần vì cần restart vLLM với flag khác nhau ở giữa).

## Đọc kết quả

Mỗi script in PASS/FAIL ra stdout và ghi JSON vào `scripts/bench/results/`. Map ngược lại quyết định treo:

| Gate | File kết quả | Nếu FAIL |
|---|---|---|
| 1 | `gate1_s2_latency.json` | Tách model nhỏ 4-8B cho S2 (ADR A3), không dùng chung 32B cho S2+S6 |
| 2 | `gate2_flags-*.json` (diff tay) | Tắt cặp flag prefix-caching/chunked-prefill trong lệnh vLLM (D3) |
| 3 | `gate3_cpu.json` (chạy thêm `--device cuda` nếu FAIL) | Chuyển embedding sang GPU-share thay vì CPU in-process (ADR B3) |
| 4 | `gate4_qwen3_clean_run.json` | Lùi về Qwen2.5-32B-Instruct (ADR A2) |

Exit code: `0` = pass, `1` = fail, `2` = thiếu dependency (chỉ gate 3).
