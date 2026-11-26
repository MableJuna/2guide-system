# ☁️ HƯỚNG DẪN TRIỂN KHAI LÊN GOOGLE CLOUD PLATFORM (GCP) — V4.0

Dự án **Hỏa Lò Smart Museum Guide V4.0** gồm Node.js Gateway (`server.js`), Python AI Engine (`ai_engine/web_server.py`), luồng Audio Streaming `.WAV` (`ffmpeg`) và kết nối ESP32. Có 2 phương án triển khai chuẩn trên GCP:

---

## 1. So sánh 2 Phương án

| Tiêu chí | Phương án 1: Compute Engine (VM Ubuntu) | Phương án 2: Cloud Run (Docker Container) |
| :--- | :--- | :--- |
| **Tương thích ESP32** | Rất cao (Static External IP, có thể ghép Nginx Reverse Proxy + Let's Encrypt) | Cao (cung cấp sẵn HTTPS endpoint, cần chọn container đủ RAM cho Node + Python) |
| **Lưu trữ dữ liệu** | Bền vững trên SSD (`data/beacons.json`, `visitor_feedback.jsonl`, `data/backups/`) | Ephemeral trừ khi mount Cloud Storage / database ngoài |
| **Vùng đề xuất** | `asia-southeast1` (Singapore) để giảm độ trễ về Việt Nam | `asia-southeast1` (Singapore) |

---

## 2. Triển khai trên Compute Engine (VM Ubuntu 22.04 LTS)

### Bước 1: Cài đặt Node.js, Python 3, FFmpeg và PM2

```bash
sudo apt-get update && sudo apt-get install -y curl git ffmpeg python3
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2
```

### Bước 2: Cấu hình Biến Môi trường (`.env`)

Tạo file `.env` trong thư mục dự án (không commit lên Git):

```env
PORT=5000
NODE_ENV=production
TRUST_PROXY=true
AI_PORT=4001
ADMIN_API_KEY=replace_with_strong_random_key_24_plus_chars
ALLOWED_ORIGINS=https://your-museum-domain.example
GROQ_API_KEY=gsk_your_groq_api_key
REQUIRE_DEVICE_AUTH=true
```

### Bước 3: Khởi chạy với PM2 & Kiểm tra Sức khỏe

```bash
pm2 start server.js --name "hoa-lo-museum-gateway"
pm2 save
curl http://127.0.0.1:5000/health
```

> [!TIP]
> `server.js` tự động khởi chạy `python3 ai_engine/web_server.py --host 127.0.0.1 --port 4001` khi Gateway boot hoặc khi nhận request `/health`, `/api/hub/ask`, `/api/feedback`. Trên VM muốn tách log AI Engine riêng có thể chạy `ai_engine/web_server.py` thành một process PM2 độc lập rồi truyền `AI_API_URL=http://127.0.0.1:4001/api/chat/ask`.

---

## 3. Triển khai trên Cloud Run từ `Dockerfile` V4.0

Image `Dockerfile` đã cấu hình sẵn Node.js + Python 3 + FFmpeg:

```bash
gcloud run deploy hoa-lo-smart-museum \
  --source . \
  --region asia-southeast1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 2 \
  --port 5000 \
  --set-env-vars "NODE_ENV=production,TRUST_PROXY=true,GROQ_API_KEY=gsk_...,ADMIN_API_KEY=..."
```
