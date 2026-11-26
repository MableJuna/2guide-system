# Hỏa Lò Groq Skill & Hybrid Grounded RAG Pack

Gói **Skill & System Prompt** chuẩn hóa cho các model trên **Groq Cloud** (`llama-3.3-70b-versatile`, `qwen/qwen3-32b`, `openai/gpt-oss-120b`, v.v.) theo **quy trình Trục Tiếng Việt (Vietnamese-Pivot 3-Stage Pipeline)**, đồng bộ toàn bộ dữ liệu từ `dataset_hoa_lo_vi` và các bộ Excel thực địa:

1. **Tiền xử lý (`preprocessor.py` + `prompts/preprocess_vi_prompt.md`)**: Nhận diện ngôn ngữ ban đầu (`vi`, `en`, `es`, `fr`, `ja`, `ko`, `zh`), chuyển mọi ngôn ngữ ngoại về Tiếng Việt, chuẩn hóa câu từ, chính tả và thuật ngữ Hỏa Lò (*Nhà tù Hỏa Lò*, *Phụ Khánh*, *Cachot*, *lập là*, *cây bàng*, *máy chém*, *cống ngầm*...), chống Prompt Injection/XSS/SQLi và phân loại chế độ trẻ em (`audience=child`).
2. **Đối soát dữ liệu gốc Tiếng Việt (`retriever.py` + `prompts/system_prompt.md`)**: Truy xuất & đối soát 100% trên nền tri thức Tiếng Việt (`Golden Facts`, **1.000 Golden Q&A `HL-001`..`HL-1000`**, **36 Atomic Fact Cards**, **28 Micro-Stories**, **12 Myth-Busters**, **6 luật Disambiguation phân định danh từ**, **6 luật Anti-Pattern `AP-01..AP-06`** và `tone_level` Cấp 1/Cấp 2 theo từng phân khu).
3. **Chuyển ngữ về ngôn ngữ ban đầu (`prompts/post_translate_prompt.md`)**: Chuyển ngữ bản đáp án đã đối soát sang đúng ngôn ngữ ban đầu của du khách, bảo toàn 100% số liệu, ngày tháng và tên riêng (với câu hỏi Tiếng Việt chỉ gọi Groq đúng 1 lượt).

## Cấu trúc thư mục

- `preprocessor.py`: Bộ tiền xử lý nhận diện ngôn ngữ, chuẩn hóa chính tả/viết tắt tiếng Việt, bắc cầu thuật ngữ đa ngôn ngữ sang Tiếng Việt.
- `prompts/system_prompt.md`: System prompt chuẩn Hybrid Grounded (trục Tiếng Việt -> đối soát dữ liệu gốc -> chuyển ngữ đầu ra).
- `prompts/preprocess_vi_prompt.md` & `prompts/post_translate_prompt.md`: Prompt chuyên biệt cho Bước 1 (dịch & chuẩn hóa sang Tiếng Việt) và Bước 3 (dịch ngược bảo toàn sự thật về ngôn ngữ ban đầu).
- `knowledge/golden_facts.json` & `golden_facts.md`: Bộ **Golden Facts & Đính chính Lỗi Sử học P0**.
- `knowledge/zones_catalog.json`: 14 phân khu chuẩn (`Z01`–`Z14`) đồng bộ đa ngôn ngữ (`vi`, `en`, `es`, `zh`, `ja`), đầy đủ hiện vật, số lượng câu hỏi theo từng bộ và `audit_baseline`.
- `knowledge/kb_golden_qa.json`: **1.000 cặp Hỏi–Đáp chuẩn lịch sử (`HL-001`..`HL-1000`)** đã trích xuất đầy đủ đáp án từ `dataset_hoa_lo_vi`.
- `knowledge/kb_bo2_questions.json`: 500 câu hỏi du khách Bộ 2 (`HL-501`..`HL-1000`) đã đồng bộ đáp án + tham chiếu chéo.
- `knowledge/kb_4lang_questions.json`: 600 câu hỏi đa ngôn ngữ (`150 English`, `150 Español`, `150 中文`, `150 日本語`) đồng bộ 14 phân khu và nối chéo tới `related_golden_qa_ids`.
- `knowledge/hoa_lo_vi_enrichments.json`: Dữ kiện nâng cao từ `dataset_hoa_lo_vi` (36 Fact Cards, 28 Micro-Stories, 12 Myth-Busters, 6 Disambiguation Rules, `tone_level` theo phân khu, 30 mẫu audit khó `mau_test_ca_kho_audit.json` và `graceful_fallback_policy`).
- `knowledge/kb_audit_dataset.json` & `knowledge/audit_anti_patterns.md`: Toàn bộ dữ liệu trích xuất từ *Báo cáo đối chiếu đánh giá AI 2Guide* (500 dòng đối chiếu, baseline 14 phân khu, 13 ca lỗi Groq Cloud AI, 11 ca Smart Guardrail từ chối nhầm, 5 khuyến nghị và 6 luật `AP-01..AP-06`).
- `knowledge/groq_eval_suite.jsonl`: Bộ test hồi quy gồm **95 ca chuẩn hóa**.
- `knowledge/kb_extended_questions.json`: Chỉ mục hợp nhất **1.600 câu hỏi** (Bộ 1 + Bộ 2 + 4 Ngôn ngữ).
- `retriever.py`: Bộ truy xuất đa ngôn ngữ `HybridHoaLoRetriever` (tích hợp disambiguation matrix, myth-busters, atomic fact cards, tone level và cảnh báo `AP-01..AP-06`).
- `groq_skill.py`: Class `HoaLoGroqSkill` và CLI chạy thử (`--dry-run`).
- `web_adapter.py` & `web_server.py`: Lớp adapter và HTTP API độc lập chuẩn hóa theo contract Web (`POST /api/chat/ask`, `POST /api/hub/ask`, `POST /api/translate`, `POST /api/feedback`, `GET /health`, `GET /stats`), tích hợp Session Memory, LRU Cache, chống Prompt Injection/XSS, chế độ plain-text cho Web/TTS và cô lập Beacon `001`–`004`.
- `scripts/build_kb.py`: Script tái tạo toàn bộ `knowledge/*.json`, `audit_anti_patterns.md` và `groq_eval_suite.jsonl` từ `dataset_hoa_lo_vi/` và 5 file `.xlsx` gốc.

## Tích hợp vào Dự án Web (`hoa_lo_smart_museum_web`)

Gói skill này được đóng gói sạch tại `hoa_lo_smart_museum_web/ai_engine/` (cổng mặc định `4001`, chế độ test `4011`) và được Node.js Gateway (`hoa_lo_smart_museum_web/server.js`) tự động khởi động/kết nối cho các luồng `/api/hub/ask`, `/api/ble-scan`, `/api/feedback` và `/health`.

## Chạy thử bằng CLI & Unit Tests

```bash
python hoa_lo_groq_skill/groq_skill.py --question "Nhà tù Hỏa Lò được xếp hạng Di tích Quốc gia năm nào?" --dry-run
python -m unittest discover -s hoa_lo_groq_skill/tests -v
```
