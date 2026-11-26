/**
 * =========================================================================================
 * UNIT TESTS — HOA LO SMART MUSEUM GATEWAY V4.0
 * Covers atomic storage, log secret redaction, BLE EMA/Hysteresis/Device isolation,
 * OWASP security validators, TTS text normalization, and V4.0 AI Engine exports.
 * =========================================================================================
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

process.env.NODE_ENV = 'test';
process.env.PORT = '0';

const { SafeJsonStore, sanitizeForLog } = require('../src/storage/safe_store');
const { BleAndDeviceManager } = require('../src/iot/ble_manager');
const {
  timingSafeEqualStr,
  validateAudioBufferMagic,
  validateBeaconPayload
} = require('../src/security/security_middleware');

const {
  sanitizeTextForSpeech,
  splitIntoAudioChunks,
  normalizeLangCode,
  isTextInLanguage,
  postPolishHeritageText,
  queryHoaLoAI,
  ensureAiEngineReady,
  stopAiEngine
} = require('../server');

// ---------------------------------------------------------------------------
// 1. SafeJsonStore & Secret Sanitization
// ---------------------------------------------------------------------------
test('SafeJsonStore writes atomically, creates rolling backups, and rolls back failed transactions', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'hoa-lo-store-'));
  const filePath = path.join(tmpDir, 'state.json');

  try {
    const store = new SafeJsonStore(filePath, { defaultData: { count: 0, items: [] } });
    assert.deepEqual(store.readSync(), { count: 0, items: [] });

    await store.writeAtomic({ count: 1, items: ['HL-001'] });
    assert.deepEqual(store.readSync(), { count: 1, items: ['HL-001'] });

    await store.updateTransaction((draft) => {
      draft.count = 2;
      draft.items.push('HL-002');
      return draft;
    });
    assert.equal(store.readSync().count, 2);
    assert.ok(store.listBackupsSync().length >= 1, 'Expected backup file to be created');

    await assert.rejects(
      store.updateTransaction(() => {
        throw new Error('simulated failure');
      }),
      /simulated failure/
    );
    assert.deepEqual(store.readSync(), { count: 2, items: ['HL-001', 'HL-002'] });
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('sanitizeForLog redacts Groq API keys, Bearer tokens, Mongo URIs, and JSON secrets', () => {
  const raw = JSON.stringify({
    api_key: 'super-secret-value',
    bearer: 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
    groq: 'gsk_1234567890abcdef',
    db: 'mongodb+srv://admin:Passw0rd123@cluster.example.net/museum'
  });
  const cleaned = sanitizeForLog(raw);
  assert.ok(!cleaned.includes('super-secret-value'));
  assert.ok(!cleaned.includes('gsk_1234567890abcdef'));
  assert.ok(!cleaned.includes('Passw0rd123'));
  assert.ok(cleaned.includes('[REDACTED_GROQ_KEY]'));
  assert.ok(cleaned.includes('Bearer [REDACTED_TOKEN]'));
});

// ---------------------------------------------------------------------------
// 2. BleAndDeviceManager (EMA, Hysteresis, Stability, Cooldown, Isolation)
// ---------------------------------------------------------------------------
test('BleAndDeviceManager isolates devices and enforces EMA, hysteresis, stability, and cooldown', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'hoa-lo-ble-'));
  try {
    const ble = new BleAndDeviceManager({
      calibrationPath: path.join(tmpDir, 'ble_cal.json')
    });

    const b1 = { id: 'beacon_1', code: '001', mac: 'AA:BB:CC:DD:EE:01', rssi_threshold: -78, cooldown_seconds: 15 };
    const b2 = { id: 'beacon_2', code: '002', mac: 'AA:BB:CC:DD:EE:02', rssi_threshold: -78, cooldown_seconds: 15 };

    // Weak signal rejected on separate device so ESP32_A EMA starts clean
    const weak = ble.evaluateBleScan({ deviceId: 'ESP32_WEAK', beacon: b1, rawRssi: -90 });
    assert.equal(weak.action, 'SKIP_WEAK_SIGNAL');

    // First strong scan triggers b1
    const first = ble.evaluateBleScan({ deviceId: 'ESP32_A', beacon: b1, rawRssi: -60 });
    assert.equal(first.action, 'TRIGGER');

    // Immediate re-scan enters cooldown
    const cd = ble.evaluateBleScan({ deviceId: 'ESP32_A', beacon: b1, rawRssi: -60 });
    assert.equal(cd.action, 'SKIP_COOLDOWN');

    // Another beacon slightly stronger (+2 dBm < +6 dBm margin) is skipped by hysteresis
    const hyst = ble.evaluateBleScan({ deviceId: 'ESP32_A', beacon: b2, rawRssi: -58 });
    assert.equal(hyst.action, 'SKIP_HYSTERESIS');

    // Much stronger b2 beats margin (-51.7 >= -54) and requires minStableHits (2) consecutive hits
    const stab1 = ble.evaluateBleScan({ deviceId: 'ESP32_A', beacon: b2, rawRssi: -40 });
    assert.equal(stab1.action, 'SKIP_STABILIZING');
    const stab2 = ble.evaluateBleScan({ deviceId: 'ESP32_A', beacon: b2, rawRssi: -40 });
    assert.equal(stab2.action, 'TRIGGER');

    // Second device ESP32_B stays completely isolated (lockedLanguage + beacon state)
    const devA = ble.getOrCreateDevice('ESP32_A');
    const devB = ble.getOrCreateDevice('ESP32_B');
    devA.lockedLanguage = 'en';
    devB.lockedLanguage = 'ja';
    assert.equal(ble.getDeviceHealthSnapshot('ESP32_A').locked_language, 'en');
    assert.equal(ble.getDeviceHealthSnapshot('ESP32_B').locked_language, 'ja');
    const bFirst = ble.evaluateBleScan({ deviceId: 'ESP32_B', beacon: b1, rawRssi: -58 });
    assert.equal(bFirst.action, 'TRIGGER');
    assert.equal(ble.detectBeaconConflicts([b1, { ...b2, mac: b1.mac }]).length, 1);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('BleAndDeviceManager records heartbeats, degraded health, and evicts stale guest devices', () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'hoa-lo-dev-'));
  try {
    const ble = new BleAndDeviceManager({
      calibrationPath: path.join(tmpDir, 'ble_cal.json')
    });
    const snap = ble.recordHeartbeat('HUB_01', {
      firmware_version: '4.0.0',
      wifi_rssi: -52,
      battery_pct: 95,
      current_code: '002'
    });
    assert.equal(snap.status, 'ONLINE');
    assert.equal(snap.firmware_version, '4.0.0');

    const staleGuest = ble.getOrCreateDevice('GUEST_OLD');
    staleGuest.lastSeenAt = Date.now() - 48 * 60 * 60 * 1000;
    ble.cleanupStaleDevices();
    assert.equal(ble.devices.has('GUEST_OLD'), false);
    assert.equal(ble.devices.has('HUB_01'), true);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------
// 3. Security Validators
// ---------------------------------------------------------------------------
test('Security helpers validate timing-safe strings, audio magic bytes, and beacon payloads', () => {
  assert.equal(timingSafeEqualStr('secret-key-1', 'secret-key-1'), true);
  assert.equal(timingSafeEqualStr('secret-key-1', 'secret-key-2'), false);
  assert.equal(timingSafeEqualStr('', ''), false);

  const wavHeader = Buffer.alloc(44);
  wavHeader.write('RIFF', 0, 'ascii');
  wavHeader.writeUInt32LE(36, 4);
  wavHeader.write('WAVE', 8, 'ascii');
  assert.equal(validateAudioBufferMagic(wavHeader, 'audio/wav').valid, true);

  const exeSpoof = Buffer.alloc(44);
  exeSpoof.write('MZ\x90\x00\x03\x00\x00\x00\x04\x00', 0, 'binary');
  assert.equal(validateAudioBufferMagic(exeSpoof, 'audio/wav').valid, false);

  assert.equal(validateBeaconPayload({ new_code: '005', mac: 'AA:BB:CC:DD:EE:05', cooldown_seconds: 15, rssi_threshold: -72 }).valid, true);
  assert.equal(validateBeaconPayload({ mac: 'INVALID_MAC', cooldown_seconds: 9999, rssi_threshold: 0 }).valid, false);
});

// ---------------------------------------------------------------------------
// 4. Server Text, Language, Speech, and V4.0 AI Engine Integration Surface
// ---------------------------------------------------------------------------
test('TTS sanitizer, audio chunk splitter, language detector, and heritage polishers work cleanly', () => {
  const spoken = sanitizeTextForSpeech('**Cây bàng** ➡️ [Chi tiết](https://example.com) — 50.000/người', 'vi');
  assert.ok(!spoken.includes('**'));
  assert.ok(!spoken.includes('➡️'));
  assert.ok(spoken.includes('tiếp theo tới'));

  const chunks = splitIntoAudioChunks('Cỗ máy chém cao 4.5m được đặt tại Nhà tù Hỏa Lò. Năm 1997 di tích được xếp hạng.', 70, 'vi');
  assert.ok(chunks.length >= 2);
  assert.ok(chunks.join(' ').includes('4.5m'));

  assert.equal(normalizeLangCode('en-US'), 'en');
  assert.equal(normalizeLangCode('zh-CN'), 'zh');
  assert.equal(normalizeLangCode('xx-unknown'), null);

  assert.equal(isTextInLanguage('The Hoa Lo Prison relic dates back to 1896.', 'en'), true);
  assert.equal(isTextInLanguage('Di tích Nhà tù Hỏa Lò được thực dân Pháp xây dựng.', 'en'), false);
  assert.equal(isTextInLanguage('火炉监狱遗址建于1896年。', 'zh'), true);

  assert.equal(postPolishHeritageText('Hoa Lo va Con Dao va Yen Bai'), 'Hỏa Lò va Côn Đảo va Yên Bái');
});

test('Gateway exposes standalone AI Engine integration exports and contains zero legacy kiemthu files', () => {
  assert.equal(typeof queryHoaLoAI, 'function');
  assert.equal(typeof ensureAiEngineReady, 'function');
  assert.equal(typeof stopAiEngine, 'function');

  const legacyDir = path.join(__dirname, '..', 'kiemthu');
  assert.equal(fs.existsSync(legacyDir), false, 'Legacy kiemthu directory must remain deleted');

  const aiSkillFile = path.join(__dirname, '..', 'ai_engine', 'groq_skill.py');
  assert.equal(fs.existsSync(aiSkillFile), true, 'Standalone ai_engine/groq_skill.py must exist');
});
