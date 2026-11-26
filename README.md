# 🏛️ HỎA LÒ SMART MUSEUM GUIDE V4.0 — WEB, IOT & VIETNAMESE-PIVOT AI

Hệ thống thuyết minh bảo tàng thông minh (Web Dashboard, Voice AI Assistant và ESP32 BLE Beacon Tour Guide) được xây dựng lại theo kiến trúc **Dual-Service V4.0**:
- **Node.js Gateway & Audio Server (`server.js`, cổng `5000`)**: Điều phối BLE đa thiết bị, bảo mật OWASP/RBAC, Web Showcase/Admin UI (`public/`) và **Single Progressive Streaming `.WAV`** qua FFmpeg pipe.
- **Standalone Python AI Engine (`ai_engine/`, cổng `4001`)**: Mô-đun trí tuệ nhân tạo **Vietnamese-Pivot 3-Stage Hybrid RAG** dựa hoàn toàn trên bộ tri thức chuẩn hóa mới **`dataset_hoa_lo_vi`**, loại bỏ hoàn toàn các phần AI cũ (`kiemthu/`, `dataset_finetune/`, Auto-Learning cũ).

---

## 🌟 Điểm Mới Trong Kiến Trúc V4.0

1. **Tri thức Chuẩn hóa `dataset_hoa_lo_vi` & Bộ Dữ liệu Đa Ngôn Ngữ**:
   - **14 phân khu di tích (`Z01`–`Z14`)** gắn sẵn thang giọng văn **`tone_level`** (Cấp 1 trang nghiêm cho Ngục tối Cachot/Máy chém/Đài tưởng niệm; Cấp 2 sắc sảo, giàu chất kể cho các khu phù hợp).
   - **1.000 cặp Hỏi–Đáp Tiếng Việt xác thực (`HL-001`..`HL-1000`)** đã trích xuất đầy đủ đáp án chuẩn sử học.
   - **36 Atomic Fact Cards**, **28 Micro-Stories (`MS-01`..`MS-28`)**, **12 Myth-Busters (`MB-01`..`MB-12`)**, và **6 Quy tắc Phân định Danh từ (`disambiguation_rules`)**.
   - **600 câu hỏi 4 ngôn ngữ (`EN/ES/ZH/JA`)** và **500 bản ghi kiểm định AI 2Guide + 6 luật `AP-01..AP-06`**.
2. **Quy trình Trục Tiếng Việt 3 Giai đoạn (`ai_engine/`)**:
   - Mọi ngôn ngữ đầu vào (`vi`, `en`, `es`, `fr`, `ja`, `ko`, `zh`) đều được chuẩn hóa/bắc cầu về Tiếng Việt, đối soát sự thật lịch sử trước khi chuyển ngữ phản hồi về ngôn ngữ ban đầu.
   - Tự động cô lập ngữ cảnh từng Beacon (`001` *Trống Đồng Đông Sơn*, `002` *Cây Bàng Lịch Sử Hỏa Lò*, `003` *Đạt Hồng*, `004` *Bảo Kiếm Hoàng Gia*).
3. **Kết nối API Đồng bộ Hai Chiều (`Node ↔ Python`)**:
   - `server.js` tự động khởi chạy và giám sát tiến trình con `ai_engine/web_server.py` (qua `ensureAiEngineReady()` / `stopAiEngine()`), kết nối hoàn chỉnh cho `/api/hub/ask`, `/api/ble-scan` (dịch đa ngôn ngữ qua `/api/translate`), `/api/feedback` và `/health`.

---

## 🚀 Khởi Động Nhanh

### Cách 1: 1-Click trên Windows
Double-click [start.bat](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/start.bat) (yêu cầu đã cài Node.js và Python 3), sau đó mở:
- Web Dashboard & Bản đồ Di tích: `http://localhost:5000`
- Trạm Giả lập ESP32 & BLE Simulator: `http://localhost:5000/test.html`
- Health Check API Gateway + AI Engine: `http://localhost:5000/health`

### Cách 2: Terminal Thủ công (Node + Python)

```bash
# Kiểm tra cú pháp JS và chạy toàn bộ bộ test tự động
node scripts/syntax_check.js
python -m unittest discover -s ai_engine/tests -v
node --test tests/unit.test.js
node --test tests/security.test.js
node --test tests/integration.test.js

# Khởi chạy hệ thống (Gateway sẽ tự bật Python AI Engine trên cổng 4001)
node server.js
```

> [!TIP]
> Để bật tổng hợp câu trả lời sinh động bằng Groq Cloud & Whisper STT, thiết lập biến môi trường `GROQ_API_KEY=gsk_...` trước khi chạy. Nếu không đặt `GROQ_API_KEY`, hệ thống vẫn trả lời chính xác bằng bộ truy xuất + tổng hợp nội bộ trên 1.000 Q&A & Fact Cards.

---

## 📊 Kết Quả Kiểm Chứng & Benchmark Thực Nghiệm

| Hạng mục | Kết quả đo thực tế | Ghi chú / Nguồn |
| :--- | :---: | :--- |
| **Syntax Lint & Tests** | **30/30 test + 10/10 file JS PASSED** | Python AI (12/12) + Node Unit (7/7) + Security (6/6) + Integration (5/5) |
| **Benchmark 1.600 câu đa ngôn ngữ** | **97.0% (1.552/1.600)** phân khu đúng | **0%** từ chối nhầm Out-of-Scope (`73.0 ms/query`) |
| **Bộ Eval 95 ca & 30 ca Audit khó** | **98.95% (94/95)** & **96.67% (29/30)** | Lưu tại `benchmarks/ai_benchmark_report.json` |
| **Load Benchmark (1 → 100 C)** | **0% errors** cả BLE & Voice Ask | `202.65 RPS` (BLE C=100) & `12.73 RPS` (Voice C=100) |

---

## 📚 Bộ Tài liệu Đầy đủ (`docs/`)

- [ARCHITECTURE.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/ARCHITECTURE.md) — Kiến trúc Dual-Service V4.0, luồng dữ liệu & danh mục module.
- [AI_ENGINE.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/AI_ENGINE.md) — Quy trình Trục Tiếng Việt 3 giai đoạn, `dataset_hoa_lo_vi`, cô lập Beacon & Groq pool.
- [API_DOCUMENTATION.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/API_DOCUMENTATION.md) — Đặc tả HTTP/SSE endpoints của Gateway `:5000` và AI Engine `:4001`.
- [SECURITY.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/SECURITY.md) — Bảo mật OWASP, Fail-Closed Admin Auth, Device RBAC SHA-256 & Anti-Injection.
- [IOT_ARCHITECTURE.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/IOT_ARCHITECTURE.md) — Bộ lọc BLE RSSI (EMA + Hysteresis + Stability + Cooldown), định vị và ESP32 Firmware.
- [TESTING.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/TESTING.md) — Chiến lược kiểm thử tự động & CI/CD pipeline.
- [BENCHMARK.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/BENCHMARK.md) — Báo cáo benchmark AI 1.600 + 95 + 30 ca và Load Benchmark 1→100 đồng thời.
- [DEPLOYMENT.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/DEPLOYMENT.md) & [GOOGLE_CLOUD_DEPLOYMENT.md](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/docs/GOOGLE_CLOUD_DEPLOYMENT.md) — Hướng dẫn triển khai Docker, Render.com và Google Cloud Platform.

---

## 📂 Cấu Trúc Thư Mục Dự Án

```
hoa_lo_smart_museum_web/
├── ai_engine/                  # Standalone Python AI Engine (Vietnamese-Pivot Hybrid RAG)
│   ├── knowledge/              # 1,000 Q&A, 14 zones, 36 fact cards, 28 stories, 12 myths, audit KB
│   ├── prompts/                # system_prompt.md, preprocess_vi_prompt.md, post_translate_prompt.md, web_style_rules.md
│   ├── tests/test_skill.py     # 12 unit & integration tests cho AI Engine
│   ├── preprocessor.py
│   ├── retriever.py
│   ├── groq_skill.py
│   ├── web_adapter.py
│   └── web_server.py           # HTTP AI microservice (:4001)
├── audio/                      # File .wav / .mp3 thuyết minh theo Beacon
├── benchmarks/                 # Benchmark scripts & JSON reports thực nghiệm
├── data/                       # beacons.json, device_keys.json, backups/
├── docs/                       # Toàn bộ tài liệu kiến trúc, AI, API, bảo mật, IoT, test, deploy
├── esp32_firmware/             # Firmware ESP32 (TLS ISRG Root X1 CA, WDT 15s, I2S INMP441/PCM5102A)
├── public/                     # Web UI Dashboard (index.html, app.js, style.css) & Simulator (test.html)
├── scripts/                    # syntax_check.js, generate_audio.py, voice_tts_fast.py
├── src/                        # iot/ble_manager.js, security/security_middleware.js, storage/safe_store.js
├── tests/                      # unit.test.js, security.test.js, integration.test.js
├── Dockerfile                  # Multi-runtime container (Node.js + Python 3 + FFmpeg)
├── render.yaml                 # Cấu hình deploy Render.com
├── package.json
├── server.js                   # Node.js Hardened Gateway & Audio Streaming Server (:5000)
└── start.bat                   # Script khởi động nhanh trên Windows
```
