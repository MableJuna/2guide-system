# 📡 IOT, BLE & ESP32 ARCHITECTURE — SMART MUSEUM GUIDE V4.0

Tài liệu đặc tả luồng xử lý BLE RSSI đa thiết bị (`src/iot/ble_manager.js`) và phần mềm nhúng ESP32 (`esp32_firmware/esp32_ble_dialogue.ino`).

---

## 1. Xử lý Tín hiệu BLE RSSI (`BleAndDeviceManager`)

Để giảm nhiễu đa đường và suy hao cơ thể người trong phòng giam tường đá, `BleAndDeviceManager.evaluateBleScan()` áp dụng chuỗi lọc 5 bước độc lập cho từng `device_id`:

1. **Hiệu chỉnh môi trường theo từng Beacon (`Calibration`)**:
   - Đọc `rssiOffset` và ngưỡng `threshold` từ `data/ble_calibration.json` (mặc định `-78 dBm`, chỉnh nóng qua `POST /api/ble/calibrate`).
2. **Exponential Moving Average (EMA) Smoothing**:
   $$\text{EMA}_t = \alpha \cdot \text{RSSI}_t + (1 - \alpha) \cdot \text{EMA}_{t-1} \quad (\alpha = 0.35)$$
   Một gói nhiễu đơn lẻ hoặc tín hiệu yếu hơn ngưỡng trả về `SKIP_WEAK_SIGNAL`.
3. **Hysteresis Margin (`+6 dBm`)**:
   - Khi thiết bị đang bám ở Beacon hiện tại (`activeBeaconId`), Beacon ứng viên chỉ vượt qua bước hysteresis khi `smoothedRssi >= activeRssi + 6` (ngược lại trả `SKIP_HYSTERESIS`).
4. **Zone Stability Counter (`minStableHits = 2`)**:
   - Yêu cầu `candidateStableCount >= 2` lần quét liên tiếp trước khi chuyển vùng (ngược lại trả `SKIP_STABILIZING`).
5. **Smart Cooldown & Conflict Detection**:
   - Cooldown theo cặp `(device_id, beacon_id)` dựa theo `beacon.cooldown_seconds` (mặc định 45s trên `data/beacons.json`), trả `SKIP_COOLDOWN` kèm `remainingSeconds` khi chưa hết hạn.
   - `detectBeaconConflicts()` chặn cấu hình Beacon trùng MAC hoặc trùng `code` với HTTP `409`.

---

## 2. Phân cấp Định vị Trong nhà

Hệ thống **không** tuyên bố định vị tọa độ `(x, y)` chính xác mức mét chỉ từ 1 thẻ BLE RSSI:

| Cấp độ | Hằng số `classifyPositioningLevel()` | Ngưỡng RSSI | Ý nghĩa thực tế |
| :--- | :--- | :--- | :--- |
| **Gần trực tiếp** | `PROXIMITY_IMMEDIATE` | `>= -60 dBm` | `< 1.5m` (ngay trước hiện vật) |
| **Trong vùng** | `ZONE_NEAR` | `-75 .. -61 dBm` | `1.5m - 4m` (trong vùng trưng bày) |
| **Cấp phòng** | `ROOM_FAR` | `-88 .. -76 dBm` | `4m - 10m` (hành lang / phòng) |
| **Ngoài tầm** | `OUT_OF_RANGE` | `< -88 dBm` | `> 10m` (ngoài vùng kích hoạt) |

---

## 3. Cô lập Đa thiết bị & Telemetry (`Multi-Device Hub`)

- Mỗi ESP32/trình duyệt có `DeviceContext` riêng biệt gồm `lockedLanguage`, `activeBeaconId`, `activeBeaconCode`, `emaRssiByBeacon`, `cooldownByBeacon`, `activeVoiceSeq` (chống phát âm thanh cũ đè câu hỏi mới) và bộ đếm thống kê riêng.
- Heartbeat `POST /api/devices/heartbeat` cập nhật `firmware_version`, `wifi_rssi`, `free_heap`, `battery_pct`, `current_code`, `last_error`.
- `getDeviceHealthSnapshot()` và `GET /api/devices/health` phân loại thiết bị thành `ONLINE`, `DEGRADED` (`stats.errors >= 10`), hoặc `OFFLINE` (`ms_since_last_seen > offlineThresholdMs`, mặc định 45s).

---

## 4. Firmware ESP32 (`esp32_firmware/esp32_ble_dialogue.ino`)

Các cấu hình bảo vệ trong mã nguồn firmware:
- `PRODUCTION_MODE = 1`: sử dụng `ISRG_ROOT_X1_CA` thay vì `setInsecure()`.
- `WDT_TIMEOUT_SEC = 15`: kích hoạt Task Watchdog 15 giây.
- Kết nối I2S: DAC `PCM5102A` (`GPIO 26 BCK`, `GPIO 25 LCK`, `GPIO 22 DIN`, amply `GPIO 21 SHDN/EN`) và Microphone `INMP441` (`I2S_NUM_1`), hỗ trợ barge-in qua nút nhấn `GPIO 0`.

> [!WARNING]
> **Phạm vi kiểm chứng**: Logic BLE RSSI, cách ly đa thiết bị, heartbeat và RBAC token đã được kiểm chứng bằng unit/security/integration test trên Node.js; việc biên dịch Arduino/PlatformIO và đo sóng thực địa trên mạch ESP32/INMP441/PCM5102A vật lý cần được kiểm tra trực tiếp trên phần cứng trước khi triển khai đại trà.
