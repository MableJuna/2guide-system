# 📊 REAL EXPERIMENTAL BENCHMARK REPORT — V4.0

> [!IMPORTANT]
> **Số liệu thực nghiệm trực tiếp**: Toàn bộ số liệu dưới đây được đo bằng hai script thực thi thật [run_ai_benchmark.py](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/benchmarks/run_ai_benchmark.py) và [run_load_benchmark.js](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/benchmarks/run_load_benchmark.js), lưu kết quả tại [ai_benchmark_report.json](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/benchmarks/ai_benchmark_report.json) và [load_benchmark_report.json](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/benchmarks/load_benchmark_report.json).

---

## 1. Benchmark AI Engine (`HoaLoGroqSkill Vietnamese-Pivot + dataset_hoa_lo_vi`)

- **Script**: `python benchmarks/run_ai_benchmark.py`
- **Tri thức nạp (`kb_totals`)**: **14** phân khu (`Z01`–`Z14`), **1.000** Golden Q&A (`HL-001`..`HL-1000`), **36** Atomic Fact Cards, **28** Micro-Stories, **12** Myth-Busters, **6** quy tắc Disambiguation, **1.600** câu hỏi mở rộng.

### 1.1 Tổng hợp 1.600 Câu hỏi Đa Ngôn Ngữ (`benchmark_1600`)
- **Độ chính xác phân khu tổng thể**: **1.552 / 1.600 (97.0%)**
- **Tỷ lệ từ chối nhầm Out-of-Scope (False OOS)**: **0 / 1.600 (0.0%)**
- **Tổng thời gian chạy**: **116.79 giây** (**73.0 ms / câu hỏi**)

| Tập dữ liệu | Đúng phân khu / Tổng | Tỷ lệ | False OOS |
| :--- | :---: | :---: | :---: |
| `bo1_vi` (500 câu Tiếng Việt Bộ 1) | **490 / 500** | **98.00%** | 0 |
| `bo2_vi` (500 câu Tiếng Việt Bộ 2) | **482 / 500** | **96.40%** | 0 |
| `4lang_en` (150 câu English) | **146 / 150** | **97.33%** | 0 |
| `4lang_es` (150 câu Español) | **143 / 150** | **95.33%** | 0 |
| `4lang_zh` (150 câu 中文) | **144 / 150** | **96.00%** | 0 |
| `4lang_ja` (150 câu 日本語) | **147 / 150** | **98.00%** | 0 |

### 1.2 Bộ Eval Suite 95 Câu & 30 Ca Audit Khó
- **`eval_suite_95`**:
  - In-scope: **90 / 91 (98.90%)**
  - Out-of-scope: **4 / 4 (100.00%)**
  - Tổng: **94 / 95 (98.95%)**
- **`hard_audit_cases` (`mau_test_ca_kho_audit.json` — 30 ca lỗi Groq + Guardrail + Dễ nhầm chéo khu)**:
  - Đạt: **29 / 30 (96.67%)**

---

## 2. Benchmark Tải Đồng thời (`benchmarks/run_load_benchmark.js`)

- **Môi trường đo**: Node.js `v26.13.0` (`win32 x64`), Node Gateway `:0` kết nối trực tiếp Python AI Engine `:4011` qua HTTP loopback.
- **Lưu ý môi trường**: Máy đo Windows cục bộ không có `ffmpeg` trong `PATH` (Gateway tự fallback sang container `.WAV` 3.244 bytes trong khi vẫn thực thi đầy đủ Node → Python AI Engine → Streaming WAV).

### 2.1 Tải BLE Scan (`POST /api/ble-scan`)

| Concurrency | Requests | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Error Rate | RSS Memory | CPU (user / sys ms) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 30 | 238.73 | 3.26 | 4.74 | 24.18 | **0%** | 55.8 MB | 63 / 15 |
| **10** | 100 | 298.49 | 32.39 | 44.08 | 45.24 | **0%** | 60.4 MB | 125 / 78 |
| **50** | 250 | 176.71 | 270.54 | 434.42 | 436.25 | **0%** | 64.8 MB | 516 / 516 |
| **100** | 400 | 202.65 | 445.89 | 836.27 | 839.32 | **0%** | 71.9 MB | 765 / 656 |

### 2.2 Tải Hỏi Đáp Đầu Cuối (`POST /api/hub/ask` — Node Gateway + Python AI Engine)

| Concurrency | Requests | RPS | P50 (ms) | P95 (ms) | P99 (ms) | Error Rate | RSS Memory | CPU (user / sys ms) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 10 | 2.16 | 430.97 | 823.80 | 823.80 | **0%** | 87.1 MB | 391 / 407 |
| **10** | 40 | 11.79 | 707.03 | 1,105.00 | 1,324.39 | **0%** | 92.0 MB | 1,390 / 1,312 |
| **50** | 100 | 12.79 | 3,328.56 | 6,322.30 | 6,699.20 | **0%** | 103.7 MB | 3,516 / 3,625 |
| **100** | 200 | 12.73 | 6,239.74 | 12,078.08 | 13,447.49 | **0%** | 129.0 MB | 6,656 / 7,500 |

---

## 3. Phạm vi Chưa Kiểm chứng trên Phần cứng Vật lý

- Chưa nạp biên dịch `esp32_firmware/esp32_ble_dialogue.ino` và đo suy hao RF BLE RSSI thực địa / thu âm INMP441 trên board ESP32 thật.
- Do môi trường kiểm thử offline không nối mạng TTS / Groq API ngoài, latency benchmark TTS + Groq Cloud thực tế (khi cấu hình `GROQ_API_KEY` + `ffmpeg` trong container) phụ thuộc mạng ngoài và chưa đo tải 100 C với FFmpeg thật.
