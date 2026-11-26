# 🚀 PRODUCTION DEPLOYMENT & OPERATIONS GUIDE — V4.0

Hướng dẫn cấu hình và triển khai hệ thống **Hỏa Lò Smart Museum Guide V4.0** (Node.js Gateway + Python AI Engine) qua Docker, Render.com hoặc máy chủ LAN.

---

## 1. Biến Môi trường (Environment Variables)

| Biến | Bắt buộc (Prod) | Mô tả | Giá trị mặc định / Ví dụ |
| :--- | :---: | :--- | :--- |
| `NODE_ENV` | ✅ | Bật strict CORS allowlist, HSTS và ẩn stack trace | `production` |
| `PORT` | ✅ | Cổng HTTP của Node Gateway (`server.js`) | `5000` (hoặc `10000` trên Render) |
| `AI_PORT` | Tùy chọn | Cổng nội bộ của Python AI Engine (`ai_engine/web_server.py`) | `4001` (`4011` khi `NODE_ENV=test`) |
| `AI_API_URL` | Tùy chọn | Ghi đè endpoint hỏi đáp AI nếu tách service riêng | `http://127.0.0.1:4001/api/chat/ask` |
| `AI_TIMEOUT_MS` | Tùy chọn | Timeout mỗi request sang Python AI Engine (ms) | `12000` |
| `ADMIN_API_KEY` | ✅ | Khóa quản trị Fail-Closed (bắt buộc cho các route Admin) | Tạo ngẫu nhiên ≥ 24 ký tự |
| `ALLOWED_ORIGINS` | ✅ | Danh sách origin được phép gọi `/api/*` trên Production | `https://your-service.onrender.com` |
| `REQUIRE_DEVICE_AUTH` | Khuyến nghị | Ép buộc `X-Device-Token` cho mọi thiết bị ESP32 | `true` |
| `GROQ_API_KEY` | Khuyến nghị | Khóa API Groq Cloud cho STT Whisper & tổng hợp LLM 3 bước (nếu thiếu vẫn chạy fallback tri thức xác thực cục bộ) | `gsk_...` |
| `RATE_LIMIT_*` | Tùy chọn | Ngưỡng Sliding-Window mỗi 60s (`GENERAL`, `VOICE`, `BLE`, `ADMIN`) | `120` / `120` / `90` / `30` |

---

## 2. Chạy Cục bộ trên Windows / Linux / macOS

- **Windows 1-click**: Chạy [start.bat](file:///c:/Users/Admin/Documents/Tài%20liệu/Antigravity/hoa_lo_smart_museum_web/start.bat) (kiểm tra `node` & `python`, khởi chạy Gateway `node server.js`, Gateway tự khởi động tiến trình con `ai_engine/web_server.py`).
- **Chạy tách 2 terminal thủ công** (tùy chọn để theo dõi log riêng):
  1. Terminal 1 (Python AI Engine): `python ai_engine/web_server.py --host 127.0.0.1 --port 4001`
  2. Terminal 2 (Node Gateway): `node server.js`
- Mở trình duyệt tại `http://localhost:5000` (Dashboard chính) hoặc `http://localhost:5000/test.html` (Simulator kiểm thử ESP32).

---

## 3. Triển khai bằng Docker & Render (`Dockerfile`, `render.yaml`)

Image `Dockerfile` cài sẵn cả Node.js, `python3` và `ffmpeg` để Node Gateway khởi chạy Python AI Engine và stream `.WAV` trong cùng container:

```bash
docker build -t hoa-lo-smart-museum:v4 .
docker run -d -p 5000:5000 \
  -e NODE_ENV=production \
  -e ADMIN_API_KEY="replace-with-strong-key" \
  -e GROQ_API_KEY="gsk_your_key" \
  -e ALLOWED_ORIGINS="https://your-domain.example" \
  hoa-lo-smart-museum:v4
```

Trên **Render.com**, sử dụng file `render.yaml` (`runtime: docker`, `healthCheckPath: /health`) và cấu hình các biến môi trường bí mật trong Render Environment Dashboard (không commit vào mã nguồn).

---

## 4. Lưu ý Vận hành & Lưu trữ

1. **Persistence cho Dữ liệu Động**: Trên container/cloud có đĩa tạm (ephemeral disk), cần gắn volume bền vững cho thư mục `data/` (`beacons.json`, `ble_calibration.json`, `device_keys.json`, `data/backups/`) và `ai_engine/knowledge/visitor_feedback.jsonl`.
2. **Rollback Cấu hình Beacon**: `SafeJsonStore` tự động tạo tối đa 5 bản sao lưu trước mỗi lần ghi tại `data/backups/`, khôi phục ngay qua `POST /api/beacons/rollback`.
3. **FFmpeg cho TTS Live Streaming**: Khi có `ffmpeg` (hoặc package `ffmpeg-static`), hệ thống giải mã MP3 → PCM 16kHz Mono trong RAM để stream `/audio-stream/*.wav` ngay lập tức; nếu thiếu `ffmpeg` trên môi trường test/offline, Gateway tự fallback buffer im lặng giữ nguyên chuẩn container `RIFF/WAVE` không crash.
