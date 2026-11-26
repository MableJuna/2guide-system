/**
 * =========================================================================================
 * INTEGRATION TESTS — HOA LO SMART MUSEUM GATEWAY V4.0 + PYTHON AI ENGINE
 * End-to-end verification:
 *   1. /health reports V4.0 + full dataset_hoa_lo_vi knowledge stats
 *   2. Multi-device BLE isolation, cooldown enforcement, heartbeat & health API
 *   3. /api/hub/ask queries real Python AI Engine, preserves Beacon 001/002 isolation,
 *      and streams valid RIFF/WAVE audio chunks
 *   4. /api/feedback validates payloads and forwards cleanly to AI Engine
 *   5. Admin Beacon Create -> Update -> Delete CRUD lifecycle with X-Admin-Key RBAC
 * =========================================================================================
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('path');

process.env.NODE_ENV = 'test';
process.env.PORT = '0';
process.env.AI_PORT = '4011';
process.env.ADMIN_API_KEY = 'test-integration-admin-key-2026';

const {
  server,
  bleManager,
  rateLimiter,
  beaconsStore,
  ensureAiEngineReady,
  stopAiEngine
} = require('../server');

let baseUrl = '';
const audioDir = path.join(__dirname, '..', 'audio');
const feedbackPath = path.join(__dirname, '..', 'ai_engine', 'knowledge', 'visitor_feedback.jsonl');
let existingAudioFiles = new Set();
let hadFeedbackBefore = false;
let previousFeedbackContent = null;

function request(method, reqPath, { body = null, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(reqPath, baseUrl);
    const data = body === null ? null : (typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
    const reqHeaders = { ...headers };
    if (data !== null && !reqHeaders['Content-Type']) {
      reqHeaders['Content-Type'] = 'application/json';
      reqHeaders['Content-Length'] = Buffer.byteLength(data);
    }
    const req = http.request({
      hostname: u.hostname,
      port: u.port,
      path: u.pathname + u.search,
      method,
      headers: reqHeaders
    }, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        let json = null;
        try { json = JSON.parse(buf.toString('utf8')); } catch (e) {}
        resolve({ status: res.statusCode, headers: res.headers, body: buf.toString('utf8'), buffer: buf, json });
      });
    });
    req.on('error', reject);
    if (data !== null) req.write(data);
    req.end();
  });
}

test.before(async () => {
  if (fs.existsSync(audioDir)) {
    existingAudioFiles = new Set(fs.readdirSync(audioDir));
  }
  hadFeedbackBefore = fs.existsSync(feedbackPath);
  if (hadFeedbackBefore) {
    previousFeedbackContent = fs.readFileSync(feedbackPath, 'utf8');
  }

  rateLimiter.reset();
  bleManager.devices.clear();

  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
  const aiUp = await ensureAiEngineReady(12000);
  assert.equal(aiUp, true, 'Python AI Engine (ai_engine/web_server.py) must boot for integration tests');
});

test.after(async () => {
  stopAiEngine();
  await new Promise((resolve) => server.close(resolve));
  await new Promise((resolve) => setTimeout(resolve, 250));
  rateLimiter.reset();

  // Remove any reply_*.wav generated during tests
  try {
    if (fs.existsSync(audioDir)) {
      for (const f of fs.readdirSync(audioDir)) {
        if (!existingAudioFiles.has(f) && f.startsWith('reply_')) {
          fs.unlinkSync(path.join(audioDir, f));
        }
      }
    }
  } catch (e) {}

  // Cleanup beacon_temp_999 if left over from an interrupted test
  try {
    const cur = beaconsStore.readSync();
    const cleaned = cur.filter((b) => b.id !== 'beacon_temp_999');
    if (cleaned.length !== cur.length) {
      beaconsStore.writeSync(cleaned, { skipBackup: true });
    }
  } catch (e) {}

  // Restore visitor_feedback.jsonl so integration tests leave no dirty test entries
  try {
    if (hadFeedbackBefore) {
      fs.writeFileSync(feedbackPath, previousFeedbackContent, 'utf8');
    } else if (fs.existsSync(feedbackPath)) {
      fs.unlinkSync(feedbackPath);
    }
  } catch (e) {}
});

test('GET /health returns V4.0 status, AI Engine readiness, and dataset_hoa_lo_vi catalog stats', async () => {
  const res = await request('GET', '/health');
  assert.equal(res.status, 200);
  assert.equal(res.json.status, 'ok');
  assert.equal(res.json.version, '4.0.0');
  assert.equal(res.json.ai_engine_ready, true);
  assert.equal(res.json.kb_stats.golden_qa, 1000);
  assert.equal(res.json.kb_stats.zones, 14);
  assert.equal(res.json.kb_stats.fact_cards, 36);
  assert.equal(res.json.kb_stats.micro_stories, 28);
  assert.equal(res.json.kb_stats.myth_busters, 12);
  assert.equal(res.json.kb_stats.disambiguation_rules, 6);
});

test('Multi-Device BLE scan isolation, cooldown, heartbeat, and device health API', async () => {
  // HUB_1 scans Beacon 001 -> TRIGGER
  const s1 = await request('POST', '/api/ble-scan', {
    body: {
      device_id: 'HUB_INTEGRATION_1',
      beacon_mac: 'AA:BB:CC:DD:EE:01',
      rssi: -58
    }
  });
  assert.equal(s1.status, 200);
  assert.equal(s1.json.status, 'success');
  assert.equal(s1.json.code, '001');

  // HUB_2 scans Beacon 001 -> isolated, also TRIGGER
  const s2 = await request('POST', '/api/ble-scan', {
    body: {
      device_id: 'HUB_INTEGRATION_2',
      beacon_mac: 'AA:BB:CC:DD:EE:01',
      rssi: -61
    }
  });
  assert.equal(s2.status, 200);
  assert.equal(s2.json.status, 'success');

  // HUB_1 immediate rescan -> SKIP_COOLDOWN
  const s1Repeat = await request('POST', '/api/ble-scan', {
    body: {
      device_id: 'HUB_INTEGRATION_1',
      beacon_mac: 'AA:BB:CC:DD:EE:01',
      rssi: -58
    }
  });
  assert.equal(s1Repeat.status, 200);
  assert.equal(s1Repeat.json.status, 'cooldown');
  assert.equal(s1Repeat.json.action, 'SKIP_COOLDOWN');

  // Heartbeat + Admin Device Health check
  const hb = await request('POST', '/api/devices/heartbeat', {
    body: {
      device_id: 'HUB_INTEGRATION_1',
      firmware_version: '4.0.0',
      wifi_rssi: -54,
      free_heap: 185000,
      battery_pct: 92,
      current_code: '001'
    }
  });
  assert.equal(hb.status, 200);
  assert.equal(hb.json.device.status, 'ONLINE');

  const health = await request('GET', '/api/devices/health', {
    headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY }
  });
  assert.equal(health.status, 200);
  assert.ok(health.json.total_devices >= 2);
});

test('POST /api/hub/ask returns grounded Vietnamese Q&A answer, WAV stream, and respects Beacon isolation', async () => {
  // 1. Historical Hỏa Lò query (verified answer in 1,000 Q&As includes year 1997 / 18/6/1997)
  const r = await request('POST', '/api/hub/ask', {
    body: {
      device_id: 'HUB_VOICE_1',
      code: '002',
      language: 'vi',
      voice_text: 'Nhà tù Hỏa Lò được xếp hạng Di tích Quốc gia từ năm nào?'
    }
  });
  assert.equal(r.status, 200);
  assert.equal(r.json.status, 'success');
  assert.ok(r.json.reply_text.includes('1997'), `Expected 1997 in reply_text, got: ${r.json.reply_text}`);
  assert.ok(r.json.audio_wav_url, 'Expected audio_wav_url');
  assert.ok(Array.isArray(r.json.chunks) && r.json.chunks.length >= 1, 'Expected chunks');

  // Fetch chunk WAV via relative URL path and validate RIFF/WAVE header
  const wavUrlObj = new URL(r.json.chunks[0].wav_url);
  const wavRes = await request('GET', wavUrlObj.pathname);
  assert.equal(wavRes.status, 200);
  assert.equal(wavRes.buffer.slice(0, 4).toString('ascii'), 'RIFF');
  assert.equal(wavRes.buffer.slice(8, 12).toString('ascii'), 'WAVE');

  // 2. Non-Hỏa Lò Beacon 001 (Trống Đồng Đông Sơn) isolation for deictic question
  const r001 = await request('POST', '/api/hub/ask', {
    body: {
      device_id: 'HUB_VOICE_001',
      code: '001',
      language: 'vi',
      voice_text: 'Giới thiệu cho tôi hiện vật này?'
    }
  });
  assert.equal(r001.status, 200);
  assert.ok(
    r001.json.reply_text.toLowerCase().includes('trống đồng') || r001.json.reply_text.toLowerCase().includes('đông sơn'),
    `Expected Beacon 001 reply to describe Trống Đồng Đông Sơn, got: ${r001.json.reply_text}`
  );
  assert.ok(!r001.json.reply_text.toLowerCase().includes('cây bàng'), 'Beacon 001 must not leak Beacon 002 Cây Bàng content');
});

test('POST /api/feedback validates payload and forwards cleanly to AI Engine', async () => {
  const bad = await request('POST', '/api/feedback', { body: {} });
  assert.equal(bad.status, 400);

  const ok = await request('POST', '/api/feedback', {
    body: {
      question: 'Cây bàng Hỏa Lò dùng để làm gì?',
      comment: 'Trả lời rõ ràng, chính xác',
      rating: 5,
      language: 'vi',
      source: 'integration-test'
    }
  });
  assert.equal(ok.status, 200);
  assert.equal(ok.json.success, true);
  assert.equal(ok.json.recorded, true);
});

test('Admin Beacon Create -> Update -> Delete CRUD lifecycle enforces X-Admin-Key', async () => {
  const addRes = await request('POST', '/api/beacons/create', {
    headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY },
    body: {
      id: 'beacon_temp_999',
      code: '999',
      mac: '11:22:33:44:55:66',
      artifact_name: 'Hiện Vật Kiểm Thử Tích Hợp',
      cooldown_seconds: 15,
      rssi_threshold: -70,
      text: 'Thuyết minh kiểm thử tạm thời.'
    }
  });
  assert.equal(addRes.status, 201);
  assert.equal(addRes.json.success, true);

  const updRes = await request('POST', '/api/beacons/update', {
    headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY },
    body: {
      id: 'beacon_temp_999',
      artifact_name: 'Hiện Vật Kiểm Thử Đã Cập Nhật'
    }
  });
  assert.equal(updRes.status, 200);
  assert.ok(updRes.json.beacons.some((b) => b.id === 'beacon_temp_999' && b.artifact_name.includes('Cập Nhật')));

  const delRes = await request('DELETE', '/api/beacons/delete?id=beacon_temp_999', {
    headers: { 'X-Admin-Key': process.env.ADMIN_API_KEY }
  });
  assert.equal(delRes.status, 200);
  assert.equal(delRes.json.success, true);
});
