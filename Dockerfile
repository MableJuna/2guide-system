# Node.js 22 + Python 3 Debian-slim hỗ trợ đồng thời Web Gateway, FFmpeg và Hỏa Lò AI Engine
FROM node:22-bullseye-slim

WORKDIR /app

# Cài đặt Python 3, ffmpeg và curl cho healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt dependencies Node.js
COPY package*.json ./
RUN npm ci --only=production || npm install --omit=dev

# Copy toàn bộ mã nguồn dự án (gồm server.js, src/, public/, data/, ai_engine/)
COPY . .

# Đảm bảo các thư mục dữ liệu và âm thanh tồn tại
RUN mkdir -p audio data logs ai_engine/knowledge

# Biến môi trường mặc định (Google Cloud Run dùng PORT=8080)
ENV NODE_ENV=production
ENV PYTHON_BIN=python3
ENV AI_PORT=4001
ENV AI_TIMEOUT_MS=12000
ENV TRUST_PROXY=true
ENV PORT=8080

EXPOSE 8080

# Kiểm tra sức khỏe cả Node Gateway & Python AI Engine
HEALTHCHECK --interval=30s --timeout=5s --start-period=12s --retries=3 \
  CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

CMD ["npm", "start"]
