"""Groq Cloud AI skill wrapper & CLI for Hỏa Lò Historical Site Q&A.

Implements the Vietnamese-Pivot 3-Stage Pipeline & Web-Compatible Groq Pool:
1. Tiền xử lý: Chuyển mọi ngôn ngữ về Tiếng Việt + chuẩn hóa câu từ, kiểm tra injection & audience.
2. Đối soát dữ liệu gốc: Truy xuất Golden Facts, Audit Anti-Patterns, Top-K Q&A & Beacon Context -> sinh đáp án Tiếng Việt.
3. Chuyển ngữ đầu ra: Chuyển bản đáp án đã đối soát sang ngôn ngữ ban đầu (và làm sạch Markdown khi ở chế độ `web`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .preprocessor import HOA_LO_GLOSSARY, preprocess_question
    from .retriever import HybridHoaLoRetriever
except ImportError:
    from preprocessor import HOA_LO_GLOSSARY, preprocess_question
    from retriever import HybridHoaLoRetriever

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_REASONING_MODELS = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]
GROQ_LIGHT_MODELS = [
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
]
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

LANG_LABELS = {
    "vi": "Tiếng Việt (Vietnamese)",
    "en": "English",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "zh": "中文 (Simplified Chinese)",
}


def strip_reasoning_tags(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models like Qwen3."""
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def clean_text_for_web(text: str) -> str:
    """Strip Markdown symbols and formatting noise so Web UI innerText and WAV TTS read cleanly."""
    s = strip_reasoning_tags(text)
    if not s:
        return ""
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*[-*•]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"(?<!\w)[*_`~]+(?!\w)", "", s)
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def _merge_usage(acc: dict[str, int], cur: dict[str, Any]) -> None:
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        val = cur.get(field)
        if isinstance(val, (int, float)):
            acc[field] = acc.get(field, 0) + int(val)


def _parse_reset_ms(raw: str | None) -> int:
    if not raw:
        return 0
    s = str(raw).strip().lower()
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return int(float(s) * 1000)
    total_ms = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)m(?!s)", s)
    sec = re.search(r"(\d+(?:\.\d+)?)s", s)
    ms = re.search(r"(\d+(?:\.\d+)?)ms", s)
    if m:
        total_ms += float(m.group(1)) * 60000
    if sec:
        total_ms += float(sec.group(1)) * 1000
    if ms:
        total_ms += float(ms.group(1))
    return int(total_ms)


class GroqModelCooldownPool:
    """Thread-safe cooldown manager for Groq multi-model failover on HTTP 429/rate-limit."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cooldown_until: dict[str, float] = {}

    def filter_candidates(self, primary: str, fallback_list: list[str], use_fallback: bool = True) -> list[str]:
        now = time.time()
        ordered = [primary]
        if use_fallback:
            for m in fallback_list:
                if m not in ordered:
                    ordered.append(m)
        with self._lock:
            fresh = [m for m in ordered if now >= self._cooldown_until.get(m, 0.0)]
            return fresh if fresh else ordered[:1]

    def mark_cooldown(self, model: str, headers: Any = None, default_sec: float = 12.0) -> None:
        wait_sec = default_sec
        if headers is not None:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            reset_tok = headers.get("x-ratelimit-reset-tokens")
            if retry_after and str(retry_after).isdigit():
                wait_sec = max(wait_sec, float(retry_after))
            elif reset_tok:
                wait_sec = max(wait_sec, _parse_reset_ms(reset_tok) / 1000.0)
        wait_sec = min(max(wait_sec, 3.0), 60.0)
        with self._lock:
            self._cooldown_until[model] = time.time() + wait_sec


class HoaLoGroqSkill:
    """Combines Vietnamese-pivot preprocessing, Hybrid RAG grounding, Web style & Groq pool."""

    def __init__(self, skill_dir: Path | None = None) -> None:
        self.skill_dir = Path(skill_dir) if skill_dir else SKILL_DIR
        prompts_dir = self.skill_dir / "prompts"
        self.base_system_prompt = (prompts_dir / "system_prompt.md").read_text(encoding="utf-8").strip()
        self.preprocess_vi_prompt = (prompts_dir / "preprocess_vi_prompt.md").read_text(encoding="utf-8").strip()
        self.post_translate_prompt = (prompts_dir / "post_translate_prompt.md").read_text(encoding="utf-8").strip()
        web_rules_path = prompts_dir / "web_style_rules.md"
        self.web_style_rules = web_rules_path.read_text(encoding="utf-8").strip() if web_rules_path.exists() else ""
        self.retriever = HybridHoaLoRetriever(self.skill_dir / "knowledge")
        self.pool = GroqModelCooldownPool()

    def _single_http_call(
        self,
        key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> tuple[str, float, dict[str, Any], str]:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["max_completion_tokens"] = max(300, max_tokens + 120)
        else:
            body["max_tokens"] = max_tokens

        req = urllib.request.Request(
            GROQ_CHAT_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
                "User-Agent": "HoaLoGroqSkill/2.1",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            raw = resp.read()
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        data = json.loads(raw.decode("utf-8"))
        choice = (data.get("choices") or [{}])[0]
        raw_reply = (choice.get("message") or {}).get("content") or ""
        return strip_reasoning_tags(raw_reply), latency_ms, (data.get("usage") or {}), (data.get("model") or model)

    def _call_groq_chat(
        self,
        key: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout: float,
        role: str = "reasoning",
        use_pool_fallback: bool = True,
    ) -> tuple[str, float, dict[str, Any], str]:
        fallback_list = GROQ_LIGHT_MODELS if role == "light" else GROQ_REASONING_MODELS
        candidates = self.pool.filter_candidates(model, fallback_list, use_fallback=use_pool_fallback)
        last_err: Exception | None = None
        for idx, cand in enumerate(candidates):
            try:
                return self._single_http_call(key, cand, messages, temperature, max_tokens, timeout)
            except urllib.error.HTTPError as err:
                last_err = err
                if err.code in (429, 500, 502, 503) and idx + 1 < len(candidates):
                    self.pool.mark_cooldown(cand, getattr(err, "headers", None))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as err:
                last_err = err
                if idx + 1 < len(candidates):
                    self.pool.mark_cooldown(cand, default_sec=8.0)
                    continue
                raise
        raise last_err if last_err else RuntimeError("Không thể kết nối Groq API.")

    def build_messages(
        self,
        question: str,
        language: str = "auto",
        zone_hint: str = "",
        beacon_code: str = "",
        top_k: int = 5,
        translated_vi: str | None = None,
        pivot_draft_vi_only: bool = False,
        artifact_context: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        response_style: str = "detailed",
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        ctx = self.retriever.retrieve(
            question=question,
            language=language,
            zone_hint=zone_hint,
            beacon_code=beacon_code,
            top_k=top_k,
            translated_vi=translated_vi,
            artifact_context=artifact_context,
        )
        target_lang = ctx["target_language"]
        target_lang_label = LANG_LABELS.get(target_lang, target_lang)
        out_lang = "vi" if pivot_draft_vi_only else target_lang
        out_lang_label = LANG_LABELS.get(out_lang, out_lang)
        intent = ctx["intent"]

        intent_guidance = (
            "Đây là câu hỏi XÁC NHẬN (Yes/No): chỉ xác nhận 'Đúng vậy' nếu nội dung câu hỏi khớp sự thật; nếu chưa hoàn toàn chính xác, nhẹ nhàng đính chính mà KHÔNG quở trách."
            if intent == "yes_no"
            else "Đây là câu hỏi MỞ: đi thẳng vào câu trả lời chi tiết ngay câu đầu tiên; KHÔNG mở đầu bằng 'Dạ đúng rồi' hay 'Yes, that is correct'."
        )

        audience_note = (
            "Đối tượng trẻ nhỏ/học sinh (audience=child): dùng ngôn từ ấm áp, đơn giản, dễ hiểu, tránh mô tả rùng rợn."
            if ctx["audience"] == "child"
            else "Đối tượng du khách phổ thông (audience=general): văn phong trang trọng, truyền cảm, chuẩn xác sử học."
        )

        gf_lines = [
            f"- [{gf['id']} | {gf['topic']}]: {gf['fact_vi']} (Cảnh báo: {gf['anti_hallucination']})"
            for gf in ctx["golden_facts"]
        ]

        qa_lines = [
            f"- [{qa['id']} | {qa['zone_vi']} | Hiện vật: {qa['artifact']}]\n"
            f"  Hỏi mẫu: {qa['question']}\n"
            f"  Đáp án chuẩn: {qa['answer']}"
            for qa in ctx["top_qa"]
        ]

        warn_lines = [
            f"- [{w['rule_id']} | {w['severity']}] Tránh lỗi '{w['pitfall']}' -> Bắt buộc: {w['guard_instruction']}"
            for w in ctx.get("audit_warnings", [])
        ]
        baseline = ctx.get("zone_audit_baseline") or {}
        if baseline.get("quality_note"):
            warn_lines.append(
                f"- [Baseline 2Guide {ctx['zone_id']} | Phủ phân khu cũ: {baseline.get('zone_coverage_rate', 0):.0%}]: {baseline['quality_note']}"
            )
        if not warn_lines:
            warn_lines.append("- Tuân thủ chặt chẽ Golden Facts và tư liệu Hỏi-Đáp chuẩn bên dưới.")

        artifact_block = ""
        active_art = ctx.get("active_artifact")
        if active_art:
            dlg = active_art.get("dialogue") or {}
            dlg_text = dlg.get("text") if isinstance(dlg, dict) else ""
            artifact_block = (
                "\n\n=== HIỆN VẬT / TRẠM BEACON TỪ WEB ===\n"
                f"- Mã trạm: {active_art.get('code', '')} | Tên hiện vật: {active_art.get('artifact_name') or active_art.get('name', '')}\n"
                f"- Vị trí trưng bày: {active_art.get('location', '')}\n"
                f"- Câu hỏi đang nhắm vào hiện vật Beacon này: {'CÓ (ưu tiên trả lời đúng hiện vật này)' if ctx.get('use_beacon_exhibit_primary') else 'Tham khảo bổ sung'}\n"
            )
            if dlg_text:
                artifact_block += f"- Thuyết minh gốc trạm Beacon: {dlg_text}\n"

        fact_cards_block = ""
        if ctx.get("fact_cards"):
            fc_lines = []
            for fc in ctx["fact_cards"][:3]:
                facts_txt = "; ".join(fc.get("verified_facts", [])[:4])
                fc_lines.append(f"- [{fc.get('card_id', '')} | {fc.get('topic', '')}]: {facts_txt}")
            if fc_lines:
                fact_cards_block = "\n\n=== ATOMIC FACT CARDS XÁC THỰC ===\n" + "\n".join(fc_lines)

        myths_block = ""
        if ctx.get("myth_busters"):
            mb_lines = [
                f"- [{mb['myth_id']}] Đính chính khéo cho lầm tưởng '{mb['common_misconception']}': {mb['truth']}"
                for mb in ctx["myth_busters"][:2]
            ]
            myths_block = "\n\n=== GIẢI MÃ HIỂU LẦM (MYTH-BUSTERS) ===\n" + "\n".join(mb_lines)

        stories_block = ""
        if response_style != "web" and ctx.get("micro_stories"):
            st_lines = [f"- [{s['story_id']} | {s['title']}]: {s['story']}" for s in ctx["micro_stories"][:2]]
            stories_block = "\n\n=== MẨU CHUYỆN HẬU TRƯỜNG BỔ SUNG ===\n" + "\n".join(st_lines)

        history_block = ""
        if conversation_history:
            hist_lines = [
                f"- {m.get('role', 'user')}: {str(m.get('content', ''))[:260]}"
                for m in conversation_history[-4:]
                if m.get("content")
            ]
            if hist_lines:
                history_block = "\n\n=== NGỮ CẢNH HỘI THOẠI GẦN ĐÂY ===\n" + "\n".join(hist_lines)

        style_block = ""
        if response_style == "web" and self.web_style_rules:
            style_block = f"\n\n=== QUY CHUẨN TRÌNH BÀY CHO WEB ({response_style}) ===\n{self.web_style_rules}"

        scope_note = (
            "Cảnh báo phạm vi: Câu hỏi này có thể nằm ngoài phạm vi Di tích / hiện vật trưng bày — chỉ trả lời nếu liên quan, ngược lại từ chối lịch sự."
            if ctx["is_likely_out_of_scope"]
            else "Xác nhận phạm vi: Câu hỏi thuộc chủ đề hợp lệ — KHÔNG được từ chối."
        )

        if response_style == "web":
            pivot_note = (
                "Hãy đối soát sự thật từ tư liệu trên và viết câu trả lời BẰNG TIẾNG VIỆT theo văn phong thuyết minh Web/TTS: 3–6 câu văn xuôi tự nhiên (~65–135 từ), KHÔNG dùng ký hiệu Markdown."
                if pivot_draft_vi_only
                else f"Hãy đối soát tri thức gốc theo trục Tiếng Việt, sau đó trả lời bằng {out_lang_label} theo văn phong thuyết minh Web/TTS (3–6 câu văn xuôi tự nhiên, KHÔNG dùng ký hiệu Markdown)."
            )
        else:
            pivot_note = (
                "Hãy xử lý, đối soát sự thật lịch sử và trả lời CHI TIẾT, MẠCH LẠC BẰNG TIẾNG VIỆT (giai đoạn lõi trước khi chuyển ngữ)."
                if pivot_draft_vi_only
                else f"Hãy đối soát tri thức gốc theo trục Tiếng Việt trên, sau đó trả lời chi tiết, mạch lạc, có cấu trúc rõ ràng bằng {out_lang_label}."
            )

        question_block = f"- Câu hỏi Tiếng Việt đã tiền xử lý & chuẩn hóa: {ctx['normalized_vi_query']}"
        if ctx["detected_language"] != "vi" or ctx["original_question"] != ctx["normalized_vi_query"]:
            question_block += f"\n- Câu hỏi gốc của du khách ({LANG_LABELS.get(ctx['detected_language'], ctx['detected_language'])}): {ctx['original_question']}"

        user_prompt = (
            f"=== THÔNG TIN ĐIỀU KHIỂN ===\n"
            f"- Ngôn ngữ mục tiêu của du khách (target_language): {target_lang_label} [code={target_lang}]\n"
            f"- Trục xử lý & đối soát trung tâm: Tiếng Việt (vi) [{ctx['pivot_method']}]\n"
            f"- Ngôn ngữ xuất ở bước này: {out_lang_label} [code={out_lang}]\n"
            f"- Chế độ trình bày: {response_style} | {audience_note}\n"
            f"- Phân khu dự kiến: {ctx['zone_id']} — {ctx['zone_names'].get('vi')} / {ctx['zone_names'].get('en', '')}\n"
            f"- Tông giọng khu vực: {ctx.get('tone_level') or 'Cấp 2 — Trang nghiêm, truyền cảm'}\n"
            f"- Intent Web dự kiến: {ctx['web_intent']}\n"
            f"- Hướng dẫn mở câu: {intent_guidance}\n"
            f"- Kiểm tra phạm vi: {scope_note}\n\n"
            f"=== GOLDEN FACTS LIÊN QUAN (ƯU TIÊN TUYỆT ĐỐI) ===\n"
            + "\n".join(gf_lines)
            + fact_cards_block
            + myths_block
            + stories_block
            + "\n\n=== CẢNH BÁO SAI SÓT ĐÃ GHI NHẬN ===\n"
            + "\n".join(warn_lines)
            + artifact_block
            + history_block
            + style_block
            + f"\n\n=== TƯ LIỆU HỎI-ĐÁP CHUẨN TRUY XUẤT (TOP-{len(ctx['top_qa'])}) ===\n"
            + "\n".join(qa_lines)
            + f"\n\n=== CÂU HỎI ĐÃ TIỀN XỬ LÝ & BẢN GỐC ===\n{question_block}\n\n"
            + pivot_note
        )

        messages = [
            {"role": "system", "content": self.base_system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return messages, ctx

    def translate_text(
        self,
        text: str,
        target_lang: str,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 4.5,
        response_style: str = "web",
    ) -> dict[str, Any]:
        """Translate museum text into target_lang preserving proper nouns & numbers."""
        clean_src = str(text or "").strip()
        lang_code = (target_lang or "vi").lower().strip().split("-")[0]
        if not clean_src or lang_code == "vi":
            return {"text": clean_src, "translated": False, "language": lang_code, "model": "passthrough"}
        key = (api_key or os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            return {"text": clean_src, "translated": False, "language": lang_code, "model": "offline"}
        msgs = self._build_post_translate_messages(
            vietnamese_answer=clean_src,
            original_question=clean_src[:120],
            target_lang=lang_code,
            response_style=response_style,
        )
        translated, lat_ms, usage, used_model = self._call_groq_chat(
            key,
            model or GROQ_LIGHT_MODELS[0],
            msgs,
            temperature=0.1,
            max_tokens=420,
            timeout=timeout,
            role="light",
            use_pool_fallback=True,
        )
        out_txt = clean_text_for_web(translated) if response_style == "web" else translated
        return {
            "text": out_txt or clean_src,
            "translated": bool(out_txt),
            "language": lang_code,
            "model": used_model,
            "latency_ms": lat_ms,
            "usage": usage,
        }

    def _build_post_translate_messages(
        self,
        vietnamese_answer: str,
        original_question: str,
        target_lang: str,
        response_style: str = "detailed",
    ) -> list[dict[str, str]]:
        target_label = LANG_LABELS.get(target_lang, target_lang)
        glossary_lines = "\n".join(f"- {vi} -> {en}" for vi, en in HOA_LO_GLOSSARY)
        style_rule = (
            "Đây là văn bản Web/TTS: xuất văn xuôi liền mạch, TUYỆT ĐỐI KHÔNG dùng dấu *, **, #, bullet thô hay ghi chú tiếng Việt trong ngoặc đơn."
            if response_style == "web"
            else "Giữ nguyên bố cục chi tiết, mạch lạc từ bản Tiếng Việt."
        )
        user_msg = (
            f"=== YÊU CẦU CHUYỂN NGỮ VỀ NGÔN NGỮ ĐÍCH ===\n"
            f"- Ngôn ngữ đích (target_language): {target_label} [code={target_lang}]\n"
            f"- Câu hỏi gốc của du khách (để khớp ngữ cảnh & văn phong): {original_question}\n"
            f"- Yêu cầu định dạng: {style_rule}\n\n"
            f"=== BẢNG THUẬT NGỮ THAM CHIẾU ===\n{glossary_lines}\n\n"
            f"=== ĐÁP ÁN TIẾNG VIỆT ĐÃ ĐỐI SOÁT DỮ LIỆU GỐC ===\n{vietnamese_answer}\n\n"
            f"Hãy chuyển ngữ toàn bộ nội dung trên sang {target_label}, giữ nguyên mọi con số, ngày tháng và tên riêng."
        )
        return [
            {"role": "system", "content": self.post_translate_prompt},
            {"role": "user", "content": user_msg},
        ]

    @staticmethod
    def _injection_refusal(target_lang: str) -> str:
        refs = {
            "vi": "Xin lỗi quý khách, tôi chỉ hỗ trợ giải đáp thông tin lịch sử và tham quan Di tích Nhà tù Hỏa Lò cũng như các hiện vật trưng bày tại đây.",
            "en": "I am sorry, I can only assist with historical information and visitor guidance for Hoa Lo Prison Relic and its museum exhibits.",
            "fr": "Désolé, je peux uniquement vous renseigner sur l'histoire et la visite du site historique de la prison Hoa Lo.",
            "es": "Lo siento, solo puedo ayudarle con información histórica y de visita sobre el sitio histórico de la prisión Hoa Lo.",
            "ja": "申し訳ございませんが、ホアロー収容所遺跡の歴史と見学案内についてのみお答えできます。",
            "ko": "죄송하지만 호아로 수용소 유적의 역사와 관람 안내에 대해서만 답변해 드릴 수 있습니다.",
            "zh": "抱歉，我只能为您提供火炉监狱历史遗迹及馆藏文物的相关讲解与参观服务。",
        }
        return refs.get(target_lang, refs["en"])

    def ask_groq(
        self,
        question: str,
        api_key: str | None = None,
        model: str = DEFAULT_GROQ_MODEL,
        language: str = "auto",
        zone_hint: str = "",
        beacon_code: str = "",
        top_k: int = 5,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout: float = 15.0,
        pipeline_mode: str = "vietnamese_pivot",
        response_style: str = "detailed",
        artifact_context: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        preprocess_model: str | None = None,
        translate_model: str | None = None,
        use_pool_fallback: bool = True,
    ) -> dict[str, Any]:
        pre_init = preprocess_question(question, language=language)
        if pre_init["is_prompt_injection"]:
            refusal = self._injection_refusal(pre_init["target_language"])
            return {
                "reply_text": refusal,
                "vietnamese_answer": self._injection_refusal("vi"),
                "original_question": pre_init["original_question"],
                "original_language": pre_init["target_language"],
                "normalized_vi_query": pre_init["normalized_vi_query"],
                "pivot_method": "security_guard",
                "pipeline_mode": pipeline_mode,
                "response_style": response_style,
                "pipeline_stages": [{"stage": "security_guard", "latency_ms": 0.0}],
                "model": "security-guard",
                "language": pre_init["target_language"],
                "zone_id": "Z01",
                "zone_name": self.retriever.zones_by_id["Z01"]["names"].get(pre_init["target_language"], ""),
                "intent": "open_fact",
                "web_intent": "OUT_OF_SCOPE",
                "retrieved_ids": [],
                "audit_warning_ids": [],
                "is_prompt_injection": True,
                "audience": pre_init["audience"],
                "latency_ms": 0.0,
                "usage": {},
            }

        key = (api_key or os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            raise ValueError("Thiếu GROQ_API_KEY (truyền tham số api_key hoặc đặt biến môi trường GROQ_API_KEY).")

        eff_max_tokens = max_tokens if max_tokens is not None else (320 if response_style == "web" else 900)
        stages: list[dict[str, Any]] = []
        total_usage: dict[str, int] = {}
        total_latency_ms = 0.0
        final_model = model

        if pipeline_mode == "single_pass":
            messages, ctx = self.build_messages(
                question=question,
                language=language,
                zone_hint=zone_hint,
                beacon_code=beacon_code,
                top_k=top_k,
                pivot_draft_vi_only=False,
                artifact_context=artifact_context,
                conversation_history=conversation_history,
                response_style=response_style,
            )
            reply_text, lat, usage, final_model = self._call_groq_chat(
                key, model, messages, temperature, eff_max_tokens, timeout,
                role="reasoning", use_pool_fallback=use_pool_fallback,
            )
            total_latency_ms += lat
            _merge_usage(total_usage, usage)
            vietnamese_answer = reply_text if ctx["target_language"] == "vi" else ""
            stages.append({"stage": "single_pass", "latency_ms": lat, "model": final_model})
        else:
            translated_vi: str | None = None
            if pre_init["detected_language"] != "vi":
                pre_msgs = [
                    {"role": "system", "content": self.preprocess_vi_prompt},
                    {"role": "user", "content": f"[{pre_init['detected_language']}] {pre_init['original_question']}"},
                ]
                translated_vi, pre_lat, pre_usage, pre_m = self._call_groq_chat(
                    key,
                    preprocess_model or model,
                    pre_msgs,
                    temperature=0.0,
                    max_tokens=200,
                    timeout=min(timeout, 4.0) if response_style == "web" else timeout,
                    role="light",
                    use_pool_fallback=use_pool_fallback,
                )
                total_latency_ms += pre_lat
                _merge_usage(total_usage, pre_usage)
                stages.append({"stage": "preprocess_to_vi", "method": "llm_translation", "model": pre_m, "latency_ms": pre_lat})
            else:
                stages.append({"stage": "preprocess_to_vi", "method": "local_vi_normalization", "latency_ms": 0.0})

            messages, ctx = self.build_messages(
                question=question,
                language=language,
                zone_hint=zone_hint,
                beacon_code=beacon_code,
                top_k=top_k,
                translated_vi=translated_vi,
                pivot_draft_vi_only=True,
                artifact_context=artifact_context,
                conversation_history=conversation_history,
                response_style=response_style,
            )
            vietnamese_answer, draft_lat, draft_usage, final_model = self._call_groq_chat(
                key,
                model,
                messages,
                temperature=temperature,
                max_tokens=eff_max_tokens,
                timeout=timeout,
                role="reasoning",
                use_pool_fallback=use_pool_fallback,
            )
            total_latency_ms += draft_lat
            _merge_usage(total_usage, draft_usage)
            stages.append({
                "stage": "vietnamese_grounded_answer",
                "model": final_model,
                "latency_ms": draft_lat,
                "normalized_vi_query": ctx["normalized_vi_query"],
                "retrieved_ids": [q["id"] for q in ctx["top_qa"]],
            })

            if ctx["target_language"] != "vi":
                tr_msgs = self._build_post_translate_messages(
                    vietnamese_answer=vietnamese_answer,
                    original_question=ctx["original_question"],
                    target_lang=ctx["target_language"],
                    response_style=response_style,
                )
                reply_text, tr_lat, tr_usage, tr_m = self._call_groq_chat(
                    key,
                    translate_model or model,
                    tr_msgs,
                    temperature=0.15,
                    max_tokens=eff_max_tokens,
                    timeout=min(timeout, 4.0) if response_style == "web" else timeout,
                    role="light",
                    use_pool_fallback=use_pool_fallback,
                )
                total_latency_ms += tr_lat
                _merge_usage(total_usage, tr_usage)
                stages.append({
                    "stage": "translate_to_original",
                    "target_language": ctx["target_language"],
                    "model": tr_m,
                    "latency_ms": tr_lat,
                })
            else:
                reply_text = vietnamese_answer

        if response_style == "web":
            reply_text = clean_text_for_web(reply_text)
            if vietnamese_answer:
                vietnamese_answer = clean_text_for_web(vietnamese_answer)

        return {
            "reply_text": reply_text,
            "vietnamese_answer": vietnamese_answer,
            "original_question": ctx["original_question"],
            "original_language": ctx["target_language"],
            "normalized_vi_query": ctx["normalized_vi_query"],
            "pivot_method": ctx["pivot_method"],
            "pipeline_mode": pipeline_mode,
            "response_style": response_style,
            "pipeline_stages": stages,
            "model": final_model,
            "language": ctx["target_language"],
            "zone_id": ctx["zone_id"],
            "zone_name": ctx["zone_names"].get(ctx["target_language"]) or ctx["zone_names"].get("vi"),
            "intent": ctx["intent"],
            "web_intent": ctx["web_intent"],
            "retrieved_ids": [q["id"] for q in ctx["top_qa"]],
            "audit_warning_ids": [w["rule_id"] for w in ctx.get("audit_warnings", [])],
            "is_prompt_injection": False,
            "audience": ctx["audience"],
            "latency_ms": round(total_latency_ms, 1),
            "usage": total_usage,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Hỏa Lò Groq Skill CLI (Vietnamese-Pivot + Web Aligned)")
    parser.add_argument("--question", "-q", required=True, help="Câu hỏi của du khách")
    parser.add_argument("--lang", "-l", default="auto", help="Mã ngôn ngữ (auto, vi, en, es, fr, ja, ko, zh)")
    parser.add_argument("--model", "-m", default=DEFAULT_GROQ_MODEL, help="Tên model Groq")
    parser.add_argument("--zone", "-z", default="", help="Gợi ý phân khu (tùy chọn)")
    parser.add_argument("--beacon-code", default="", help="Mã BLE Beacon web (vd: 002)")
    parser.add_argument("--mode", default="vietnamese_pivot", choices=["vietnamese_pivot", "single_pass"])
    parser.add_argument("--style", default="detailed", choices=["detailed", "web"])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in context tiền xử lý, truy xuất và prompt, không gọi Groq API")
    args = parser.parse_args()

    skill = HoaLoGroqSkill()
    if args.dry_run:
        msgs, ctx = skill.build_messages(
            args.question,
            language=args.lang,
            zone_hint=args.zone,
            beacon_code=args.beacon_code,
            top_k=args.top_k,
            pivot_draft_vi_only=(args.mode == "vietnamese_pivot"),
            response_style=args.style,
        )
        print(json.dumps({
            "original_language": ctx["original_language"],
            "detected_language": ctx["detected_language"],
            "target_language": ctx["target_language"],
            "normalized_vi_query": ctx["normalized_vi_query"],
            "pivot_method": ctx["pivot_method"],
            "normalization_notes": ctx["normalization_notes"],
            "response_style": args.style,
            "audience": ctx["audience"],
            "intent": ctx["intent"],
            "web_intent": ctx["web_intent"],
            "zone_id": ctx["zone_id"],
            "zone_names": ctx["zone_names"],
            "is_likely_out_of_scope": ctx["is_likely_out_of_scope"],
            "top_qa_ids": [q["id"] for q in ctx["top_qa"]],
            "audit_warning_ids": [w["rule_id"] for w in ctx.get("audit_warnings", [])],
            "matched_extended": ctx["matched_extended"],
        }, ensure_ascii=False, indent=2))
        print("\n--- USER PROMPT PREVIEW ---\n")
        print(msgs[1]["content"])
    else:
        out = skill.ask_groq(
            args.question,
            model=args.model,
            language=args.lang,
            zone_hint=args.zone,
            beacon_code=args.beacon_code,
            top_k=args.top_k,
            pipeline_mode=args.mode,
            response_style=args.style,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
