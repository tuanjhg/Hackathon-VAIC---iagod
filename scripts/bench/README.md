# Benchmark gate Phase 0

Việc "PHẢI benchmark ở Phase 0" — bảng cuối `docs/research/dmx-tech-decisions.md`. Mỗi gate ra một quyết định treo (model, CPU/GPU, fallback version), không phải một feature.

**Revised 18/07 (ADR A2''):** model chính đổi sang **Qwen3.6-27B qua API key OpenRouter**, không tự host vLLM, không dùng FPT AI Factory. Gate 1/3/4 vẫn áp dụng — chỉ trỏ biến môi trường sang OpenRouter. **Gate 2 (cặp flag prefix-caching/chunked-prefill) archived** — không có server tự host để chỉnh flag, không chạy nữa.

**Không chạy được trong sandbox này** — Gate 1/4 cần endpoint LLM thật, Gate 3 cần tải model embedding qua mạng. Script đã viết sẵn, sẵn sàng chạy ngay khi có API key.

## Chạy

```bash
export VLLM_BASE_URL=https://openrouter.ai/api/v1   # OpenRouter
export VLLM_MODEL=qwen/qwen3.6-27b                   # XÁC NHẬN đúng slug thật trong catalog OpenRouter

python3 scripts/bench/gate1_s2_latency.py          # p95 S2 <700ms?

pip install -r scripts/bench/requirements-bench.txt
python3 scripts/bench/gate3_embedding_latency.py   # p95 embedding CPU <30ms/query?
python3 scripts/bench/gate4_qwen3_clean_run.py     # 10/10 call sạch (guided_json + hermes tool)?
```

Hoặc `make bench-gates` (gate1+3+4).

**Archived — không chạy trong kế hoạch hiện tại:** `gate2_vllm_flags.py` (đo cặp flag prefix-caching/chunked-prefill) — chỉ có ý nghĩa khi tự host vLLM, xem `docker-compose.vllm.yml` (archived) và ADR A2''.

## Đọc kết quả

Mỗi script in PASS/FAIL ra stdout và ghi JSON vào `scripts/bench/results/`. Map ngược lại quyết định treo:

| Gate | File kết quả | Nếu FAIL |
|---|---|---|
| 1 | `gate1_s2_latency.json` | Tách model nhỏ hơn cho S2 (ADR A3), không dùng chung model cho S2+S6 |
| 3 | `gate3_cpu.json` (chạy thêm `--device cuda` nếu FAIL) | Chuyển embedding sang GPU-share thay vì CPU in-process (ADR B3) |
| 4 | `gate4_qwen3_clean_run.json` | Route OpenRouter cho model này không hỗ trợ đúng guided_json/tool-call như kỳ vọng — cần sửa `apps/api/src/router/client.py`, xem ADR A2'' |

Exit code: `0` = pass, `1` = fail, `2` = thiếu dependency (chỉ gate 3).
