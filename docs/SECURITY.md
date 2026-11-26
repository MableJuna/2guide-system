# 🛡️ CYBERSECURITY ARCHITECTURE & HARDENING REPORT — V4.0

Tài liệu đặc tả các lớp bảo mật của **Hỏa Lò Smart Museum Gateway V4.0** (`src/security/security_middleware.js`) và bộ lọc đầu vào trong Python AI Engine (`ai_engine/preprocessor.py`). Toàn bộ yêu cầu Gateway được kiểm chứng tự động bởi `tests/security.test.js` (`6/6 passed`).

---

## 1. Threat Model & Ma trận Phòng thủ

| Mối đe dọa | Mức độ | Biện pháp phòng thủ V4.0 | Bằng chứng kiểm thử |
| :--- | :---: | :--- | :--- |
| Truy cập Admin CRUD Beacon / Device Key khi thiếu cấu hình env | **P0** | **Fail-Closed Admin Auth** (`verifyAdminRequest`): trả `503` khi thiếu `ADMIN_API_KEY`, trả `401` khi sai key, so sánh bằng `crypto.timingSafeEqual` (`timingSafeEqualStr`) | `Security 2` |
| CORS Wildcard `*` ở môi trường Production | **P0** | Vô hiệu `*` khi `NODE_ENV=production` hoặc `RENDER` được đặt; chỉ chấp nhận `ALLOWED_ORIGINS` hoặc same-host; trả `403` cho origin không hợp lệ trên `/api/*` | `Security 1` |
| Giả mạo thiết bị ESP32 gửi BLE/Voice/Heartbeat trái phép | **P0** | `DeviceAuthManager`: cấp token tiền tố `esp_`, lưu băm SHA-256 trên `data/device_keys.json` (không lưu plaintext), hỗ trợ thu hồi tức thì qua `/api/devices/revoke` | `Security 3` |
| Tải lên file giả mạo `audio/wav` (HTML/Script/EXE) hoặc JSON quá cỡ | **P0** | `MAX_JSON_BYTES = 64 KB` (`413`), `MAX_AUDIO_BYTES = 5 MB` (`413`), kiểm định **binary magic bytes** (`validateAudioBufferMagic`: `RIFF/WAVE`, `WebM`, `OggS`, `ID3/MP3`, `MP4/M4A`, `fLaC`) trả `415` | `Security 4`, `Unit 5` |
| Flood / Brute-force API (General, Voice, BLE, Admin) | **P1** | `RateLimiter` sliding-window theo IP với 4 tier riêng biệt (`general: 120`, `voice: 120`, `ble: 90`, `admin: 30` req/60s), trả `429` kèm `Retry-After` | `Security 5` |
| Lộ secret key, Bearer token, password hoặc stack trace ra ngoài | **P1** | `safeErrorResponse()` ẩn stack trace; `sanitizeForLog()` che `gsk_*`, `Bearer *`, password trong Mongo URI và các trường JSON nhạy cảm | `Security 6`, `Unit 2` |
| Prompt Injection / Jailbreak / XSS / SQLi vào AI | **P1** | `sanitize_and_guard_input()` trong `ai_engine/preprocessor.py` phát hiện chỉ dẫn ghi đè vai trò, `<script>`, SQL/template payload; log feedback lưu tách biệt khỏi KB xác thực | `ai_engine/tests` |
| MITM trên kết nối HTTPS của ESP32 (`setInsecure()`) | **P0** | Firmware `esp32_firmware/esp32_ble_dialogue.ino` đặt `#define PRODUCTION_MODE 1` dùng chứng chỉ gốc `ISRG_ROOT_X1_CA` | Kiểm tra tĩnh mã nguồn (chưa chạy trên mạch ESP32 thật) |

---

## 2. Phân quyền RBAC 3 Vai trò

1. **Guest (Khách tham quan / Web Showcase)**: Gọi các endpoint công khai (`/health`, `/api/info`, `/api/state`, `/api/beacons`, `/api/events`, `/api/hub/ask`, `/api/feedback`, `/audio-stream/*`, `/audio/*`) trong giới hạn CORS và Rate Limit.
2. **Device (ESP32 Hub)**: Gửi `X-Device-Token` cùng `device_id`. Sau khi thiết bị được cấp token bằng `/api/devices/issue-key` (hoặc bật `REQUIRE_DEVICE_AUTH=true`), mọi request thiếu/sai/đã thu hồi token đều bị từ chối `401`.
3. **Admin (Quản trị viên Bảo tàng)**: Yêu cầu `X-Admin-Key` (hoặc `Bearer <ADMIN_API_KEY>`). Luôn fail-closed khi biến `ADMIN_API_KEY` trống. Áp dụng cho `/api/beacons/create`, `/api/beacons/update`, `/api/beacons/delete`, `/api/beacons/rollback`, `/api/ble/calibrate`, `/api/devices/issue-key`, `/api/devices/revoke`, `/api/devices/health`.

---

## 3. OWASP HTTP Security Headers

`applySecurityHeaders()` gắn tự động trên mọi response của Gateway:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), camera=(), microphone=(self)`
- `X-XSS-Protection: 0`
- `Content-Security-Policy`: giới hạn `default-src 'self'`, `media-src 'self' blob: data:`, `connect-src 'self'`
- `Strict-Transport-Security`: `max-age=31536000; includeSubDomains` (trên Production hoặc kết nối qua `x-forwarded-proto: https`)
