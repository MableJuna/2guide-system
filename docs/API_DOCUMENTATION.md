# 📡 API DOCUMENTATION — HỎA LÒ SMART MUSEUM GATEWAY V4.0

Tài liệu đặc tả các HTTP/SSE endpoint của Node.js Gateway (`server.js` v4.0, mặc định cổng `5000`) và Python AI Engine nội bộ (`ai_engine/web_server.py`, mặc định cổng `4001`).

**Base URL (Gateway Local)**: `http://localhost:5000`  
**Base URL (AI Engine Internal)**: `http://127.0.0.1:4001`

---

## 1. Xác thực, Giới hạn Payload & Rate Limit

| Vai trò | Header xác thực | Phản hồi khi vi phạm |
| :--- | :--- | :--- |
| **Guest** | Không yêu cầu token (kiểm soát `ALLOWED_ORIGINS` khi `NODE_ENV=production`) | `403 Forbidden` (CORS sai), `429 Too Many Requests` |
| **Device** | `X-Device-Token: <token>` + `device_id` (bắt buộc khi thiết bị đã cấp key hoặc `REQUIRE_DEVICE_AUTH=true`) | `401 Unauthorized` |
| **Admin** | `X-Admin-Key: <ADMIN_API_KEY>` hoặc `Authorization: Bearer <ADMIN_API_KEY>` (**Fail-Closed**) | `503 Service Unavailable` (thiếu env key), `401 Unauthorized` (sai key) |

**Giới hạn đầu vào (`src/security/security_middleware.js`):**
- JSON payload tối đa: `65,536 bytes` (`64 KB`) → vượt ngưỡng trả `413`.
- Audio upload tối đa: `5,242,880 bytes` (`5 MB`) → vượt ngưỡng trả `413`; sai magic-byte âm thanh (`.wav`, `.webm`, `.ogg`, `.mp3`, `.m4a`, `.flac`) trả `415`.
- Rate Limit theo IP (`windowMs = 60s`): `general: 120`, `voice: 120`, `ble: 90`, `admin: 30` (ghi đè qua `RATE_LIMIT_*`).

---

## 2. Public & Visitor Endpoints (Gateway `:5000`)

### `GET /health` (alias: `GET /api/health`)
Tự động đảm bảo Python AI Engine sẵn sàng (`ensureAiEngineReady()`) và trả về thống kê tri thức `dataset_hoa_lo_vi`.
- **Response `200`**:
```json
{
  "status": "ok",
  "version": "4.0.0",
  "uptime_sec": 12,
  "ffmpeg_bin": "ffmpeg",
  "ai_engine_url": "http://127.0.0.1:4001/api/chat/ask",
  "ai_engine_ready": true,
  "kb_stats": {
    "zones": 14,
    "golden_qa": 1000,
    "extended_questions": 1600,
    "audit_records": 500,
    "fact_cards": 36,
    "micro_stories": 28,
    "myth_busters": 12,
    "disambiguation_rules": 6
  },
  "groq_key_configured": false
}
```

### `GET /api/info` & `GET /api/state`
- `GET /api/info`: Thông tin gateway V4.0, IP mạng LAN phục vụ nạp ESP32 và URL AI Engine.
- `GET /api/state`: Trạng thái hiện tại (`latestBeacon`, `latestVoice`, `lockedLanguage`, `isVoiceProcessing`).

### `GET /api/language` & `POST /api/language`
- `GET`: Lấy ngôn ngữ đang khóa và danh sách 6 ngôn ngữ hỗ trợ (`vi`, `en`, `fr`, `ja`, `ko`, `zh`).
- `POST`: Khóa ngôn ngữ toàn cục `{ "language": "en" }` và phát SSE `LANGUAGE_CHANGED`.

### `GET /api/beacons` & `GET /api/events`
- `GET /api/beacons`: Danh sách hiện vật BLE Beacon trong `data/beacons.json`.
- `GET /api/events`: Luồng Server-Sent Events (SSE) đẩy realtime sự kiện `BEACON_TRIGGERED`, `VOICE_RESPONSE`, `LANGUAGE_CHANGED`.

### `POST /api/hub/ask` (aliases: `/api/voice-query`, `/api/hub-query`, `/api/esp32/ask`)
Gửi câu hỏi bằng JSON hoặc audio nhị phân/multipart để hỏi Python AI Engine và nhận âm thanh **Single Progressive Streaming `.WAV`**.
- **Rate Limit Tier**: `voice`
- **Request JSON**:
```json
{
  "device_id": "ESP32_HUB_01",
  "code": "002",
  "language": "vi",
  "voice_text": "Nhà tù Hỏa Lò được xếp hạng Di tích Quốc gia từ năm nào?"
}
```
- **Response `200`**:
```json
{
  "status": "success",
  "action": "PLAY_VOICE_REPLY",
  "current_artifact": "Cây Bàng Lịch Sử Hỏa Lò",
  "code": "002",
  "question": "Nhà tù Hỏa Lò được xếp hạng Di tích Quốc gia từ năm nào?",
  "reply_text": "...",
  "ai_source": "HoaLoWebAdapter (Vietnamese-Pivot Offline Grounded)",
  "locked_language": "vi",
  "audio_mode": "SINGLE_STREAMING_WAV",
  "audio_wav_url": "http://localhost:5000/audio-stream/reply_1795674033113.wav",
  "total_chunks": 3,
  "chunks": [
    { "index": 1, "text": "...", "status": "ready", "wav_url": "http://localhost:5000/audio-stream/reply_1795674033113.wav" }
  ],
  "voice_seq": 1,
  "superseded": false
}
```

### `GET /audio-stream/:streamId.wav` & `HEAD /audio-stream/:streamId.wav`
Stream file `.WAV` 16kHz Mono 16-bit liền mạch (`RIFF/WAVE`). Khi file đã gộp xong trên đĩa, hỗ trợ `Accept-Ranges: bytes`.

### `POST /api/feedback`
Chuyển tiếp phản hồi đánh giá của du khách sang Python AI Engine để ghi log kiểm định append-only (`ai_engine/knowledge/visitor_feedback.jsonl`).
- **Body**: `{ "question": "...", "reply": "...", "rating": 5, "comment": "...", "device_id": "GUEST", "language": "vi" }`
- **Response `200`**: `{ "success": true, "recorded": true, "entry": { ... } }` (thiếu cả `question` và `comment` trả `400`).

---

## 3. IoT & ESP32 Endpoints

### `POST /api/ble-scan` (alias: `POST /api/beacon-trigger`)
Nhận tín hiệu BLE RSSI từ ESP32/Web Simulator và lọc qua `BleAndDeviceManager`.
- **Body**: `{ "device_id": "ESP32_01", "beacon_mac": "AA:BB:CC:DD:EE:01", "rssi": -60, "language": "vi" }`
- **Response `200`**:
  - Khi kích hoạt: `{ "status": "success", "action": "PLAY_AUDIO", "code": "001", "artifact_name": "...", "dialogue": { ... }, "audio": { "wav_url": "...", "mp3_url": "..." } }`
  - Khi bị lọc/cooldown: `{ "status": "cooldown" | "filtered", "action": "SKIP_COOLDOWN" | "SKIP_WEAK_SIGNAL" | "SKIP_HYSTERESIS" | "SKIP_STABILIZING", ... }`

### `POST /api/devices/heartbeat` (alias: `POST /api/device/heartbeat`)
Cập nhật telemetry định kỳ cho ESP32 (`firmware_version`, `wifi_rssi`, `free_heap`, `battery_pct`, `current_code`, `last_error`).
- **Response `200`**: `{ "success": true, "device": { "device_id": "...", "status": "ONLINE", ... } }`

---

## 4. Admin Management Endpoints (Fail-Closed RBAC)

Tất cả endpoint sau bắt buộc header `X-Admin-Key` và chịu giới hạn Rate Limit tier `admin`:

| Method | Endpoint | Chức năng |
| :--- | :--- | :--- |
| `POST` | `/api/beacons/create` | Tạo Beacon mới (validate format + chặn trùng MAC/code trả `409` + atomic write, trả `201`) |
| `POST` | `/api/beacons/update` | Cập nhật nội dung/MAC/cooldown/ngưỡng RSSI Beacon (`200`) |
| `DELETE` / `POST` | `/api/beacons/delete` | Xóa Beacon theo `?id=...`, `?code=...` hoặc JSON body (`200`) |
| `POST` | `/api/beacons/rollback` | Khôi phục `data/beacons.json` từ bản sao lưu gần nhất trong `data/backups/` |
| `POST` | `/api/ble/calibrate` | Hiệu chỉnh `threshold` và `rssi_offset` cho từng Beacon (`data/ble_calibration.json`) |
| `POST` | `/api/devices/issue-key` | Cấp mới / xoay vòng token thiết bị `{ "device_id": "ESP32_01" }` (trả `token` tiền tố `esp_`) |
| `POST` | `/api/devices/revoke` | Thu hồi quyền truy cập thiết bị `{ "device_id": "ESP32_01", "reason": "..." }` |
| `GET` | `/api/devices/health` | Lấy danh sách toàn bộ thiết bị cùng trạng thái `ONLINE` / `DEGRADED` / `OFFLINE` |

---

## 5. Standalone Python AI Engine Endpoints (`ai_engine/web_server.py :4001`)

| Method | Endpoint | Chức năng |
| :--- | :--- | :--- |
| `GET` | `/health` | Trả về `status: "UP"`, thống kê `kb_stats` đầy đủ từ `dataset_hoa_lo_vi` và `groqConfigured` |
| `GET` | `/stats` | Trả về số phiên hoạt động, số lượt hỏi/phản hồi, tỷ lệ Groq vs offline |
| `POST` | `/api/chat/ask` | Trả lời theo JSON `{ question, sessionId, language, artifactContext, response_style }` |
| `POST` | `/api/hub/ask` | Alias chuẩn hóa payload trả thêm các trường tương thích IoT Voice Hub |
| `POST` | `/api/translate` | Dịch thuật ngữ di sản theo yêu cầu Node Gateway (`{ text, targetLang, sourceLang }`) |
| `POST` | `/api/feedback` | Ghi log phản hồi du khách vào `ai_engine/knowledge/visitor_feedback.jsonl` |
