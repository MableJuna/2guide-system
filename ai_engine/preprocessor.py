"""Vietnamese-pivot preprocessing, normalization, security guard, and glossary for Hỏa Lò Q&A.

Workflow:
1. Sanitize input (strip HTML/script noise, detect prompt injection/jailbreaks & child audience).
2. Detect original language & normalize text (Unicode NFC, whitespace, abbreviations, typos).
3. Translate / pivot any non-Vietnamese query into normalized Vietnamese before KB grounding.
4. Preserve original question + target language metadata for localization back to the visitor's language.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Canonical bilingual glossary injected into Stage 1 (to VI) and Stage 3 (back to original lang)
HOA_LO_GLOSSARY: list[tuple[str, str]] = [
    ("Nhà tù Hỏa Lò / Maison Centrale", "Hỏa Lò Prison (Maison Centrale)"),
    ("Làng Phụ Khánh", "Phụ Khánh village"),
    ("Ngục tối (Cachot)", "Cachot dark solitary cells"),
    ("Khu D & Xà lim tử hình", "Zone D & Death Row solitary cells"),
    ("Máng tôn lập là", "galvanized iron communal food trough ('lập là')"),
    ("Cống ngầm vượt ngục", "underground drainage sewer escape route"),
    ("Cây bàng lịch sử", "historic tropical almond tree (Cây bàng)"),
    ("Việt Nam Quốc dân Đảng", "Việt Nam Quốc dân Đảng (Vietnamese Nationalist Party)"),
    ("Đông Kinh Nghĩa Thục", "Đông Kinh Nghĩa Thục (Tonkin Free School movement)"),
    ("Hanoi Hilton / Mật mã Tap Code", "'Hanoi Hilton' / Tap Code"),
    ("Tour Đêm thiêng liêng", "'Sacred Night' ('Đêm thiêng liêng') experiential tour"),
]

# Ordered longest-first / specific-first to safely normalize Vietnamese typos, ASR mishearings & unaccented terms.
# IMPORTANT: Only run on Vietnamese text (either natively VI or after Stage 1 translation into VI).
_VI_NORMALIZATION_RULES: list[tuple[str, str]] = [
    (r"\bnh[aà]\s+t[uù]\s+h[oò][aả]\s+l[oò]\b", "Nhà tù Hỏa Lò"),
    (r"\bnt\s+h[oò][aả]\s+l[oò]\b", "Nhà tù Hỏa Lò"),
    (r"\bh[oò][aả]\s+l[oò]\b", "Hỏa Lò"),
    (r"\bmaison\s+centrale\b", "Maison Centrale"),
    (r"\b(?:ca\s*s[oốôơ]t|ca\s*s[oô]c|ka\s*s[oô]t|ca-?chot)\b", "ngục tối Cachot"),
    (r"\bcachot\b", "Cachot"),
    (r"\b(?:pbc|phan\s+b[oộ]i\s+ch[aâ]u)\b", "Phan Bội Châu"),
    (r"\b(?:lvc|l[uươ][ơo]ng\s+v[aă]n\s+can)\b", "Lương Văn Can"),
    (r"\b(?:nth|nguy[eễ]n\s+th[aá]i\s+h[oọ]c)\b", "Nguyễn Thái Học"),
    (r"\b(?:hqv|ho[aà]ng\s+qu[oố]c\s+vi[eệ]t)\b", "Hoàng Quốc Việt"),
    (r"\b(?:đknt|dknt|dong\s+kinh\s+nghia\s+thuc)\b", "Đông Kinh Nghĩa Thục"),
    (r"\b(?:vnqdđ|vnqdd)\b", "Việt Nam Quốc dân Đảng"),
    (r"\bphu\s+khanh\b", "Phụ Khánh"),
    (r"\byen\s+bai\b", "Yên Bái"),
    (r"\bcon\s+dao\b", "Côn Đảo"),
    (r"\bson\s+la\b", "Sơn La"),
    (r"\bquan\s+su\b", "Quán Sứ"),
    (r"\btho\s+nhuom\b", "Thợ Nhuộm"),
    (r"\bhang\s+co\b", "Hàng Cỏ"),
    (r"\blap\s+la\b", "lập là"),
    (r"\bcay\s+bang\b", "cây bàng"),
    (r"\bmay\s+chem\b", "máy chém"),
    (r"\bcong\s+ngam\b", "cống ngầm"),
    (r"\bvuot\s+nguc\b", "vượt ngục"),
    (r"\bxa\s+lim\b", "xà lim"),
    (r"\btu\s+chinh\s+tri\b", "tù chính trị"),
    (r"\bphi\s+cong\s+my\b", "phi công Mỹ"),
    (r"\bdai\s+tuong\s+niem\b", "đài tưởng niệm"),
    (r"\bphu\s+dieu\b", "phù điêu"),
    (r"\bdem\s+thieng\s+lieng\b", "Đêm thiêng liêng"),
    (r"\bdi\s+tich\s+quoc\s+gia\b", "Di tích Quốc gia"),
    (r"\bxep\s+hang\b", "xếp hạng"),
    (r"\bkhau\s+phan\b", "khẩu phần"),
    (r"\bbao\s+chi\b", "báo chí"),
    (r"\bkhan\s+tay\b", "khăn tay"),
    (r"\bbat\s+sat\b", "bát sắt"),
    (r"\bmai\s+ngoi\b", "mái ngói"),
    (r"\bso\s+dang\s+ky\b", "sổ đăng ký"),
    (r"\bgio\s+mo\s+cua\b", "giờ mở cửa"),
    (r"\bgia\s+ve\b", "giá vé"),
    (r"\bve\s+vao\s+cong\b", "vé vào cổng"),
    (r"\bgui\s+xe\b", "gửi xe"),
    (r"\bxe\s+lan\b", "xe lăn"),
    (r"\bnha\s+ve\s+sinh\b", "nhà vệ sinh"),
    (r"\bchup\s+anh\b", "chụp ảnh"),
    (r"\btrong\s+dong\b", "trống đồng"),
    (r"\bdong\s+son\b", "Đông Sơn"),
    (r"\bdai\s+hong\s+chung\b", "Đại Hồng Chung"),
    (r"\bbao\s+kiem\b", "Bảo Kiếm"),
]

_VI_FILLER_PREFIXES = re.compile(
    r"^(?:xin\s+chào|chào\s+(?:bạn|em|anh|chị|ad|ai|hướng\s+dẫn\s+viên)|cho\s+(?:tôi|mình|em)\s+hỏi(?:\s+một\s+chút)?|làm\s+ơn\s+cho\s+hỏi)\s*[,:\-–]?\s*",
    re.IGNORECASE,
)

_PROMPT_INJECTION_RE = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?|disregard\s+(?:all\s+)?(?:previous|system)\s+prompts?|"
    r"bypass\s+(?:safety|guardrails?|rules?)|reveal\s+(?:your\s+)?system\s+prompt|you\s+are\s+now\s+(?:dan|developer\s+mode)|"
    r"bỏ\s+qua\s+(?:tất\s+cả|mọi)\s+(?:quy\s+tắc|chỉ\s+dẫn|hướng\s+dẫn)|quên\s+(?:hết|toàn\s+bộ)\s+vai\s+trò|"
    r"tiết\s+lộ\s+system\s+prompt|(?:union\s+select|drop\s+table|<script\b|javascript:|onerror\s*=))",
    re.IGNORECASE,
)

_CHILD_AUDIENCE_RE = re.compile(
    r"(?:cho\s+(?:bé|trẻ\s+em|trẻ\s+nhỏ|các\s+em\s+nhỏ|học\s+sinh\s+tiểu\s+học)|giải\s+thích\s+đơn\s+giản\s+(?:cho\s+(?:bé|con|trẻ))|"
    r"for\s+(?:kids?|children|a\s+child)|explain\s+to\s+(?:a\s+)?(?:kid|child)|child[- ]friendly|"
    r"para\s+niños|pour\s+(?:les\s+)?enfants|子供向け|子ども向け|小学生向け|어린이용|给孩子|儿童)",
    re.IGNORECASE,
)

_DEICTIC_EXHIBIT_RE = re.compile(
    r"(?:hiện\s+vật\s+này|vật\s+này|cái\s+này|cổ\s+vật\s+này|trước\s+mặt|đang\s+đứng\s+ở\s+đâu|tôi\s+ở\s+đâu|chỗ\s+này|"
    r"giới\s+thiệu(?:\s+chung)?(?:\s+về)?(?:\s+hiện\s+vật)?(?:\s+này|\s+đi)?$|đây\s+là\s+(?:gì|đâu)|"
    r"this\s+(?:exhibit|artifact|object|item|room|zone)|what\s+is\s+this|where\s+am\s+i|in\s+front\s+of\s+me|"
    r"este\s+(?:objeto|artefacto)|qué\s+es\s+esto|cet\s+objet|この展示|これは何|这是什么|이것은)",
    re.IGNORECASE,
)


def sanitize_and_guard_input(text: str) -> tuple[str, bool]:
    """Strip HTML tags/control noise and detect prompt-injection or script payloads."""
    raw = unicodedata.normalize("NFC", text or "")
    is_injection = bool(_PROMPT_INJECTION_RE.search(raw))
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, is_injection


def detect_audience(text: str) -> str:
    """Detect whether visitor requested child-friendly wording."""
    return "child" if _CHILD_AUDIENCE_RE.search(text or "") else "general"


def is_deictic_exhibit_query(text: str) -> bool:
    """True when visitor refers deictically to the artifact/station in front of them."""
    return bool(_DEICTIC_EXHIBIT_RE.search(text or ""))


def detect_language(text: str) -> str:
    """Detect visitor query language among vi, en, es, fr, ja, ko, zh."""
    if not text:
        return "vi"
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    # Vietnamese-exclusive letters & tone marks (absent in Spanish/French)
    if re.search(
        r"[ăâđêôơưĂÂĐÊÔƠƯảãạắằẳẵặấầẩẫậẻẽẹếềểễệỉĩịỏõọốồổỗộớờởỡợủũụứừửữựỳỷỹỵ"
        r"ẢÃẠẮẰẲẴẶẤẦẨẪẬẺẼẸẾỀỂỄỆỈĨỊỎÕỌỐỒỔỖỘỚỜỞỠỢỦŨỤỨỪỬỮỰỲỶỸỴ]",
        text,
    ):
        return "vi"
    if re.search(
        r"[¿¡ñÑ]|(\b(?:qué|cómo|cuál|dónde|por qué|visita|prisión|disculpe|celda|alcantarillado|guillotina|almendro|hacia|sobre)\b)",
        text,
        re.I,
    ):
        return "es"
    if re.search(
        r"[çœæÇŒÆ]|(\b(?:bonjour|pourquoi|combien|quelle|prisons|musée|est-ce|guillotine)\b)",
        text,
        re.I,
    ):
        return "fr"
    if re.search(
        r"\b(?:của|và|những|trong|được|không|tù|hỏa|lò|nào|gì|sao|nha tu hoa lo|cay bang|may chem|cong ngam|xa lim|vuot nguc|xep hang)\b",
        text,
        re.I,
    ):
        return "vi"
    return "en"


def normalize_vietnamese_text(text: str) -> tuple[str, list[str]]:
    """Normalize Unicode, whitespace, typos, and Hỏa Lò proper terms in a Vietnamese string."""
    cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()
    notes: list[str] = []

    stripped = _VI_FILLER_PREFIXES.sub("", cleaned).strip()
    if stripped and stripped != cleaned:
        cleaned = stripped
        notes.append("stripped_conversational_filler")

    for pattern, replacement in _VI_NORMALIZATION_RULES:
        updated = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if updated != cleaned:
            notes.append(f"normalized_term:{replacement}")
            cleaned = updated

    cleaned = re.sub(r"\s+([?!.,:;])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned, notes


def build_offline_vietnamese_pivot(
    question: str,
    original_language: str,
    concept_terms_vi: list[str],
    zone_vi_hint: str = "",
) -> str:
    """Construct a structured Vietnamese pivot query offline from cross-lingual concepts & proper nouns."""
    q_clean = re.sub(r"\s+", " ", unicodedata.normalize("NFC", question or "")).strip()
    years_nums = re.findall(r"\b\d{3,4}\b", q_clean)
    proper_hits = re.findall(
        r"\b(?:Maison Centrale|Hanoi Hilton|Tap Code|Cachot|Yen Bai|Phu Khanh|Con Dao|Son La|Phan Boi Chau|Nguyen Thai Hoc|Luong Van Can|Hoang Quoc Viet|McCain|B-?52|Dong Son|Dai Hong Chung|Bao Kiem)\b",
        q_clean,
        re.IGNORECASE,
    )
    parts: list[str] = []
    if zone_vi_hint:
        parts.append(f"Phân khu {zone_vi_hint}")
    dedup_terms: list[str] = []
    for t in concept_terms_vi + proper_hits + years_nums:
        if t and t.lower() not in {d.lower() for d in dedup_terms}:
            dedup_terms.append(t)
    if dedup_terms:
        norm_terms, _ = normalize_vietnamese_text(" ".join(dedup_terms[:10]))
        parts.append(norm_terms)
    summary = " — ".join(parts) if parts else q_clean
    return f"[Chuyển ngữ khái niệm về Tiếng Việt từ {original_language}]: {summary}"


def preprocess_question(
    question: str,
    language: str = "auto",
    translated_vi_text: str | None = None,
    concept_terms_vi: list[str] | None = None,
    zone_vi_hint: str = "",
) -> dict[str, Any]:
    """Full preprocessing record: sanitize + security guard + audience + normalized VI pivot."""
    raw_clean, is_injection = sanitize_and_guard_input(question)
    detected_lang = detect_language(raw_clean)
    target_lang = detected_lang if (not language or language == "auto") else language.lower().strip().split("-")[0]
    audience = detect_audience(raw_clean)
    deictic_exhibit = is_deictic_exhibit_query(raw_clean)

    if translated_vi_text and translated_vi_text.strip():
        normalized_vi, notes = normalize_vietnamese_text(translated_vi_text)
        notes.insert(0, f"llm_translated_from:{detected_lang}")
        pivot_method = "llm_translation"
        if audience == "general":
            audience = detect_audience(normalized_vi)
        deictic_exhibit = deictic_exhibit or is_deictic_exhibit_query(normalized_vi)
    elif detected_lang == "vi":
        normalized_vi, notes = normalize_vietnamese_text(raw_clean)
        pivot_method = "native_vi_normalized"
    else:
        normalized_vi = build_offline_vietnamese_pivot(
            raw_clean,
            original_language=detected_lang,
            concept_terms_vi=concept_terms_vi or [],
            zone_vi_hint=zone_vi_hint,
        )
        notes = [f"offline_concept_bridge_from:{detected_lang}"]
        pivot_method = "offline_concept_bridge"

    return {
        "original_question": raw_clean,
        "detected_language": detected_lang,
        "original_language": target_lang,
        "target_language": target_lang,
        "normalized_vi_query": normalized_vi,
        "pivot_method": pivot_method,
        "normalization_notes": notes,
        "is_prompt_injection": is_injection,
        "audience": audience,
        "is_deictic_exhibit": deictic_exhibit,
    }
