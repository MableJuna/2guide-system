# 🧪 TESTING & CI/CD QUALITY GATE — V4.0

Tài liệu đặc tả các tầng kiểm thử tự động và quy trình kiểm tra hợp nhất cho **Hỏa Lò Smart Museum Gateway V4.0 + Python AI Engine (`ai_engine/`)**.

---

## 1. Tháp Kiểm thử (Test Suites)

| Tầng kiểm thử | Lệnh chạy | Tập tin | Kết quả xác minh |
| :--- | :--- | :--- | :---: |
| **Static Syntax Lint** | `node scripts/syntax_check.js` | `scripts/syntax_check.js` | **10 / 10 JS files valid** |
| **Python AI Unit Tests** | `python -m unittest discover -s ai_engine/tests -v` | `ai_engine/tests/test_skill.py` | **12 / 12 PASSED** |
| **Node Gateway Unit Tests** | `node --test tests/unit.test.js` | `tests/unit.test.js` | **7 / 7 PASSED** |
| **Security & RBAC Tests** | `node --test tests/security.test.js` | `tests/security.test.js` | **6 / 6 PASSED** |
| **Gateway + AI Integration** | `node --test tests/integration.test.js` | `tests/integration.test.js` | **5 / 5 PASSED** |
| **AI Dataset Benchmark** | `python benchmarks/run_ai_benchmark.py` | `benchmarks/run_ai_benchmark.py` | **97.0%** (1.600 Q), **0** false OOS, **29/30** audit |
| **HTTP Concurrency Load** | `node benchmarks/run_load_benchmark.js` | `benchmarks/run_load_benchmark.js` | **0% errors** (C=1 / 10 / 50 / 100) |

---

## 2. Chi tiết Phạm vi Kiểm thử

### 2.1 Python AI Engine (`ai_engine/tests/test_skill.py` — 12 tests)
- Kiểm đếm đầy đủ tri thức `dataset_hoa_lo_vi`: 14 phân khu, 1.000 Golden Q&A, 36 Fact Cards, 28 Micro-Stories, 12 Myth-Busters, 6 luật phân định, 500 Bộ 2, 600 câu 4 ngôn ngữ, 500 dòng Audit 2Guide và 95 eval cases.
- Tiền xử lý & 3-Stage Vietnamese Pivot (`en`/`es`/`zh`/`ja` + viết tắt không dấu tiếng Việt).
- Quy tắc phân định thực thể, Myth-Busters, Tone Level Cấp 1 vs Cấp 2, lọc thẻ `<think>`, Groq 429 failover, HTTP endpoints (`/api/chat/ask`, `/api/translate`, `/api/feedback`) và cô lập Beacon `001`–`004`.

### 2.2 Node Gateway Unit Tests (`tests/unit.test.js` — 7 tests)
1. `SafeJsonStore`: atomic write, rolling backups, rollback giao dịch lỗi.
2. `sanitizeForLog`: che `gsk_*`, `Bearer *`, MongoDB URI password và secret JSON.
3. `BleAndDeviceManager`: làm mượt EMA, lọc tín hiệu yếu (`SKIP_WEAK_SIGNAL`), hysteresis `+6 dBm`, 2-hit stability, cooldown, cô lập đa thiết bị và phát hiện xung đột MAC (`detectBeaconConflicts`).
4. `BleAndDeviceManager`: heartbeat & thu hồi guest device quá hạn.
5. `Security middleware`: `timingSafeEqualStr`, kiểm tra magic byte `.WAV` thật vs file giả mạo `MZ`, validate Beacon payload.
6. Helpers Gateway: `sanitizeTextForSpeech`, `splitIntoAudioChunks`, `normalizeLangCode`, `isTextInLanguage`, `postPolishHeritageText`.
7. Kiểm tra export API Engine (`queryHoaLoAI`, `ensureAiEngineReady`, `stopAiEngine`) và đảm bảo không còn thư mục cũ `kiemthu/`.

### 2.3 Security Tests (`tests/security.test.js` — 6 tests, `NODE_ENV=production`)
1. OWASP HTTP headers (`nosniff`, `DENY`, `CSP`, `HSTS`) và tắt hoàn toàn wildcard CORS `*`.
2. Fail-Closed Admin Auth (`503` khi thiếu `ADMIN_API_KEY`, `401` khi sai key, `400` khi MAC sai).
3. Device Authentication RBAC: `/api/devices/issue-key` → `/api/devices/heartbeat` (`200` / `401` khi sai token) → `/api/devices/revoke` → bị chặn `401`.
4. Chặn file giả mạo `audio/wav` (`415`) và JSON > 64KB (`413`).
5. Rate Limiter trả `429 Too Many Requests` + `Retry-After`.
6. Lỗi hệ thống không rò rỉ stack trace hoặc đường dẫn nội bộ.

### 2.4 Integration Tests (`tests/integration.test.js` — 5 tests)
1. `GET /health`: xác nhận `version === "4.0.0"`, `ai_engine_ready === true`, `golden_qa === 1000`, `fact_cards === 36`, `micro_stories === 28`, `myth_busters === 12`, `disambiguation_rules === 6`.
2. Multi-Device BLE scan isolation (`HUB_INTEGRATION_1` vs `HUB_INTEGRATION_2`), cooldown (`SKIP_COOLDOWN`), heartbeat (`POST /api/devices/heartbeat`) và `GET /api/devices/health`.
3. `POST /api/hub/ask`: câu hỏi lịch sử Hỏa Lò qua Python AI Engine + phát container `RIFF/WAVE`, kèm kiểm tra cô lập Beacon `001` (*Trống Đồng Đông Sơn*) không rò rỉ nội dung Cây Bàng (`002`).
4. `POST /api/feedback`: từ chối `400` khi rỗng, trả `200` khi chuyển tiếp thành công sang AI Engine.
5. Admin Beacon Create (`201`) → Update (`200`) → Delete (`200`) với `X-Admin-Key`.

---

## 3. Pipeline CI/CD (`.github/workflows/ci.yml`)

GitHub Actions cài đặt Node.js 22 + Python 3.12 + `ffmpeg`, chạy tuần tự: lint JS → Python AI unit tests → Node unit tests → Node security tests → Node integration tests → AI benchmark.
