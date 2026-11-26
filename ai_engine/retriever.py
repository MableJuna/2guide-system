"""Hybrid multilingual retriever for Hỏa Lò Knowledge Base (VI, EN, ES, FR, JA, KO, ZH)."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .preprocessor import detect_language, preprocess_question
except ImportError:
    from preprocessor import detect_language, preprocess_question

SKILL_DIR = Path(__file__).resolve().parent
KB_DIR = SKILL_DIR / "knowledge"

_STOPWORDS = {
    "và", "của", "các", "có", "trong", "được", "cho", "về", "với", "tại", "khi", "này", "đó",
    "những", "một", "như", "từ", "đến", "hay", "hoặc", "thì", "mà", "nào", "gì", "sao", "tại sao",
    "không", "nhé", "ạ", "dạ", "quý", "khách", "bạn", "tôi", "phải", "đúng", "hỏa", "lò", "nhà", "tù",
    "the", "is", "are", "was", "were", "in", "on", "at", "of", "to", "and", "or", "for", "with",
    "what", "which", "who", "when", "where", "why", "how", "this", "that", "from", "prison", "hoa", "lo",
    "el", "la", "los", "las", "de", "del", "en", "y", "por", "para", "con", "que", "qué", "cómo", "cárcel",
    "le", "les", "des", "du", "dans", "pour", "avec", "qui", "quoi",
}

# Cross-lingual concept bridge: maps multilingual terms -> (zone_boosts, vietnamese_expansion_terms)
_CONCEPT_ALIASES: list[tuple[str, list[str], list[str]]] = [
    (r"maison centrale|phu khanh|phụ khánh|pottery|kiln|stove|cerámic|alfarer|horno|火炉|富庆|陶|窯|ホアロー|호아로|chòi gác|cổng chính|main gate|puerta principal|正门|正門|trapezoid|1896|1899|1997|1993|xếp hạng|di tích quốc gia|vữa|gạch trần|mái ngói|khu tây|european", ["Z01"], ["cổng chính", "phụ khánh", "maison centrale", "1896", "1899", "1997", "1993", "xếp hạng", "khu tây", "mái ngói", "tường gạch"]),
    (r"collective|colectiva|集体|集団|tập thể|cùm chân|shackle|grilletes|peephole|mirilla|khe|hở|slot|lập là|lap la|máng tôn|ration|ración|khẩu phần|cơm hẩm|cá mắm|bát sắt|thùng vệ sinh|bucket|cubo|tráng men|cuenco|bowl|食器|食事|饭|米|配給", ["Z02"], ["phòng giam tập thể", "khe đưa cơm", "khẩu phần", "cơm", "cá mắm", "lập là", "bát sắt", "thùng vệ sinh", "cùm"]),
    (r"cachot|dark cell|celda oscura|solitary|dốc ngược|sloped|inclinad|黑牢|禁闭|暗闇独房|カショ|독방", ["Z03"], ["cachot", "ngục tối", "xà lim đơn", "dốc ngược", "bệ xi măng"]),
    (r"zone d|zona d|death row|corredor de la muerte|死囚|死刑囚|khu d|xà lim tử hình|cùm gỗ lim|ironwood", ["Z04"], ["khu d", "xà lim tử hình", "tử tù", "cùm gỗ lim", "noel 1951"]),
    (r"guillotin|断头台|ギロチン|단두대|máy chém|lưỡi dao|blade|cuchilla|刃|45 độ|yên bái|yen bai|nguyễn thái học|nguyen thai hoc|khởi nghĩa|công cụ tra tấn|tortur|gông", ["Z05"], ["máy chém", "lưỡi dao", "yên bái", "nguyễn thái học", "40", "50", "2 m", "4 m", "sọt mây", "tra tấn"]),
    (r"women|woman|mujer|女监|女性監房|여성|child|children|niño|niña|儿童|子ども|trại giam nữ|nữ tù|tù nhi|quang thái|sinh con", ["Z06"], ["trại giam nữ", "nữ tù", "tù nhi", "trẻ em", "nguyễn thị quang thái"]),
    (r"sewer|alcantarill|tunnel|fuga|escape|下水道|越狱|脱獄|脱走|cống ngầm|nắp cống|vượt ngục|1945|1951|quán sứ|thợ nhuộm|thăng thiên", ["Z07"], ["cống ngầm", "vượt ngục", "1945", "1951", "nắp cống", "quán sứ", "5 chiến sĩ", "thăng thiên"]),
    (r"almond|almendr|榄仁|モモタマナ|amandier|cây bàng|lá bàng|búp bàng|vỏ bàng|quả bàng|gỗ bàng|sân trại", ["Z08"], ["cây bàng", "lá bàng", "búp bàng", "vỏ bàng", "gỗ bàng", "sân trại"]),
    (r"school|escuela|press|prensa|newspaper|periódico|学校|报刊|新聞|秘密|trường học|báo chí|viết tay|mực vô hình|bút chì|ống sậy|hoàng quốc việt|chi bộ|đảng|1931|1932", ["Z09"], ["trường học", "báo chí", "mực vô hình", "bút chì", "ống sậy", "hoàng quốc việt", "chi bộ", "1931"]),
    (r"relic|reliquia|keepsake|recuerdo|遗物|遺品|kỷ vật|handkerchief|pañuelo|手帕|ハンカチ|khăn tay|thêu|phan bội châu|lương văn can|đông kinh nghĩa thục|trung chuyển|hàng cỏ|côn đảo|sơn la", ["Z10"], ["kỷ vật", "khăn tay", "phan bội châu", "lương văn can", "đông kinh nghĩa thục", "trung chuyển", "ga hàng cỏ", "côn đảo", "sơn la"]),
    (r"pilot|piloto|pow|american|estadounidense|美军|飞行员|パイロット|捕虜|phi công mỹ|hanoi hilton|mccain|1964|1972|1973|b-52|b52|sấm rền|rolling thunder|linebacker|điện biên phủ trên không|cắt tóc|giáng sinh|tap code", ["Z11"], ["phi công mỹ", "1964", "1972", "1973", "b-52", "hanoi hilton", "sấm rền", "nhân đạo", "cắt tóc", "tap code"]),
    (r"monument|monumento|memorial|conmemorativo|bas-relief|bajorrelieve|纪念碑|浮雕|慰霊碑|レリーフ|đài tưởng niệm|phù điêu|bức phù điêu", ["Z12"], ["đài tưởng niệm", "phù điêu", "tưởng nhớ"]),
    (r"functional|dependencias|功能区|機能施設|infirmary|enfermería|kitchen|cocina|registry|registro|sổ sách|lăn vân tay|bệnh xá|nhà bếp|xưởng|khu chức năng|nhập trại", ["Z13"], ["khu chức năng", "sổ sách", "vân tay", "nhập trại", "bệnh xá", "nhà bếp"]),
    (r"sacred night|noche sagrada|神圣之夜|ナイトツアー|night tour|tour đêm|đêm thiêng liêng|audioguide|audio guide|souvenir|recuerdo|纪念品|お土産|túi tote|giờ mở cửa|opening hours|ticket|vé|bảo tồn|trải nghiệm|hoạt cảnh", ["Z14"], ["đêm thiêng liêng", "tour đêm", "audioguide", "lưu niệm", "bảo tồn", "mở cửa", "đặt vé", "hoạt cảnh"]),
]

_BEACON_TO_ZONES = {
    "002": ["Z08"],
}


def map_to_web_intent(
    intent: str,
    zone_id: str,
    norm_q: str,
    is_out_of_scope: bool,
    is_injection: bool,
    use_beacon_exhibit: bool,
) -> str:
    """Map internal query intent & zone into Web Gateway v3.0 intent labels."""
    if is_injection or is_out_of_scope:
        return "OUT_OF_SCOPE"
    if use_beacon_exhibit:
        return "EXHIBIT_INFORMATION"
    if re.search(r"(giá vé|mua vé|vé vào|miễn phí|ticket\s*price|entrance\s*fee|admission|cuánto\s+cuesta|门票|入場料)", norm_q):
        return "TICKET_INFORMATION"
    if re.search(r"(giờ mở cửa|mấy giờ|đóng cửa|opening\s*hours|horario|qué\s+hora|开放时间|開館時間)", norm_q):
        return "OPENING_HOURS"
    if re.search(r"(đêm thiêng liêng|tour đêm|sacred\s*night|noche\s*sagrada|audioguide|audio\s*guide|thuyết minh|hướng dẫn viên|đặt tour|lịch trình)", norm_q):
        return "GUIDED_TOUR_BOOKING"
    if re.search(r"(gửi xe|đỗ xe|parking|nhà vệ sinh|toilet|restroom|xe lăn|wheelchair|người khuyết tật|chụp ảnh|quay phim|trang phục|quà lưu niệm|túi tote|hành lý|tủ gửi đồ)", norm_q):
        return "FACILITY_SUPPORT"
    if re.search(r"(cấp cứu|khẩn cấp|y tế|bảo vệ|thất lạc|đồ rơi|emergency|medical|lost)", norm_q):
        return "EMERGENCY_SUPPORT"
    if zone_id == "Z14" and intent == "general":
        return "GUIDED_TOUR_BOOKING"
    return "HISTORICAL_FACT"


def _evaluate_beacon_binding(
    artifact_ctx: dict[str, Any] | None,
    combined_norm: str,
    is_deictic: bool,
    has_hoa_lo_topic: bool,
) -> tuple[bool, list[str]]:
    """Decide whether query targets the active Web BLE beacon exhibit itself."""
    if not artifact_ctx:
        return False, []
    code = str(artifact_ctx.get("code") or "").strip()
    art_name = _norm(str(artifact_ctx.get("artifact_name") or artifact_ctx.get("name") or ""))
    loc = _norm(str(artifact_ctx.get("location") or ""))
    # Map beacon artifact words (excluding ultra-generic terms) to check explicit user mention
    art_tokens = [t for t in _tokenize(art_name) if t not in {"lich", "su", "lịch", "sử", "cổ", "đô", "triều", "nguyễn"}]
    explicit_artifact_hit = bool(art_tokens) and (
        sum(1 for t in art_tokens if re.search(rf"\b{re.escape(t)}\b", combined_norm)) >= min(2, len(art_tokens))
    )
    is_hoa_lo_beacon = code == "002" or ("hỏa lò" in f"{art_name} {loc}") or ("hoa lo" in f"{art_name} {loc}")
    if explicit_artifact_hit:
        return True, (["Z08"] if is_hoa_lo_beacon else [])
    if is_deictic and not has_hoa_lo_topic:
        return True, (["Z08"] if is_hoa_lo_beacon else [])
    return False, (["Z08"] if (is_hoa_lo_beacon and is_deictic) else [])


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "").strip().lower())


def classify_intent(question: str) -> str:
    q = _norm(question)
    if re.search(
        r"(phải không|đúng không|có phải|có đúng|có từng|đúng chứ|is it true|was it|did they|were there|are these|"
        r"¿es cierto|¿fue|¿realmente|est-ce que|是不是|本当に|ですか\??$)",
        q,
    ):
        return "yes_no"
    if re.search(r"(bao nhiêu|mấy|năm nào|khi nào|tại sao|vì sao|ai|ở đâu|cơ chế|như thế nào|what|why|how|when|who|where|which|cuándo|por qué|cómo|为什么|いつ|なぜ)", q):
        return "open_fact"
    return "general"


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zà-ỹ0-9]+|[\u4e00-\u9fff]|[\u3040-\u30ff]+|[\uac00-\ud7af]+", _norm(text))
    return [t for t in tokens if (t not in _STOPWORDS and len(t) > 1) or bool(re.match(r"[\u4e00-\u9fff\d]", t))]


def _char_trigrams(text: str) -> Counter[str]:
    s = _norm(text)
    if len(s) < 3:
        return Counter([s]) if s else Counter()
    return Counter(s[i : i + 3] for i in range(len(s) - 2))


def _tri_norm(c: Counter[str]) -> float:
    return math.sqrt(sum(v * v for v in c.values()))


def _cosine(a: Counter[str], na: float, b: Counter[str], nb: float) -> float:
    if not na or not nb:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    return dot / (na * nb)


class HybridHoaLoRetriever:
    """Fast cross-lingual retriever across Golden Facts, 500 Golden Q&A, and 1,600 indexed questions."""

    def __init__(self, kb_dir: Path | None = None) -> None:
        self.kb_dir = Path(kb_dir) if kb_dir else KB_DIR
        self.zones: list[dict[str, Any]] = json.loads((self.kb_dir / "zones_catalog.json").read_text(encoding="utf-8"))
        self.golden_facts: list[dict[str, Any]] = json.loads((self.kb_dir / "golden_facts.json").read_text(encoding="utf-8"))["golden_facts"]
        self.golden_qa: list[dict[str, Any]] = json.loads((self.kb_dir / "kb_golden_qa.json").read_text(encoding="utf-8"))
        self.extended_q: list[dict[str, Any]] = json.loads((self.kb_dir / "kb_extended_questions.json").read_text(encoding="utf-8"))

        audit_path = self.kb_dir / "kb_audit_dataset.json"
        if audit_path.exists():
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            self.pitfall_rules: list[dict[str, Any]] = audit_data.get("pitfall_rules", [])
            self.audit_baselines_by_zone: dict[str, dict[str, Any]] = {
                zb["zone_id"]: zb for zb in audit_data.get("zone_baselines", [])
            }
            self.audit_records_count: int = len(audit_data.get("audit_records", []))
            self.groq_audit_cases: list[dict[str, Any]] = audit_data.get("groq_cloud_ai_cases", [])
            self.guardrail_false_refusals: list[dict[str, Any]] = audit_data.get("smart_guardrail_false_refusals", [])
            self.audit_recommendations: list[dict[str, Any]] = audit_data.get("technical_recommendations", [])
        else:
            self.pitfall_rules = []
            self.audit_baselines_by_zone = {}
            self.audit_records_count = 0
            self.groq_audit_cases = []
            self.guardrail_false_refusals = []
            self.audit_recommendations = []

        self.zones_by_id = {z["zone_id"]: z for z in self.zones}
        self.qa_by_id = {q["id"]: q for q in self.golden_qa}
        self.pitfall_rules_by_id = {r["rule_id"]: r for r in self.pitfall_rules}

        enrich_path = self.kb_dir / "hoa_lo_vi_enrichments.json"
        if enrich_path.exists():
            enr = json.loads(enrich_path.read_text(encoding="utf-8"))
            self.fact_cards: list[dict[str, Any]] = enr.get("fact_cards", [])
            self.micro_stories: list[dict[str, Any]] = enr.get("micro_stories", [])
            self.myth_busters: list[dict[str, Any]] = enr.get("myth_busters", [])
            self.disambiguation_rules: list[dict[str, Any]] = enr.get("disambiguation_rules", [])
            self.graceful_fallback_policy: dict[str, Any] = enr.get("graceful_fallback_policy", {})
        else:
            self.fact_cards = []
            self.micro_stories = []
            self.myth_busters = []
            self.disambiguation_rules = []
            self.graceful_fallback_policy = {}

        self.fact_cards_by_id = {c["card_id"]: c for c in self.fact_cards if "card_id" in c}
        self.stories_by_id = {s["story_id"]: s for s in self.micro_stories if "story_id" in s}
        for mb in self.myth_busters:
            mb["_tokens"] = set(_tokenize(f"{mb.get('common_misconception', '')} {mb.get('truth', '')}"))

        # Precompute token sets, trigrams & norms for fast retrieval
        for item in self.golden_qa:
            item["_tokens"] = set(_tokenize(f"{item['zone_vi']} {item['artifact']} {item['question']} {item['answer']}"))
            item["_q_tokens"] = set(_tokenize(f"{item['artifact']} {item['question']}"))
            tri = _char_trigrams(f"{item['artifact']} {item['question']}")
            item["_tri"] = tri
            item["_tri_norm"] = _tri_norm(tri)

        for item in self.extended_q:
            item["_tokens"] = set(_tokenize(f"{item['zone_label']} {item['artifact']} {item['question']}"))
            tri = _char_trigrams(item["question"])
            item["_tri"] = tri
            item["_tri_norm"] = _tri_norm(tri)

    def is_obviously_out_of_scope(
        self,
        question: str,
        zone_scores: dict[str, float],
        best_qa_score: float,
        is_injection: bool = False,
        use_beacon_exhibit: bool = False,
    ) -> bool:
        if is_injection:
            return True
        if use_beacon_exhibit:
            return False
        q = _norm(question)
        domain_hit = bool(re.search(
            r"hỏa lò|hoa lo|maison centrale|phụ khánh|phu khanh|cachot|cây bàng|máy chém|guillotin|"
            r"cống ngầm|xà lim|tù nhân|tù chính trị|chiến sĩ|phan bội châu|lương văn can|hoàng quốc việt|"
            r"đông kinh nghĩa thục|ga hàng cỏ|sổ đăng ký|mái ngói|thùng vệ sinh|cắt tóc|sấm rền|"
            r"điện biên phủ trên không|khăn tay|chạm khắc|phi công|hanoi hilton|đêm thiêng liêng|bảo tàng|di tích|"
            r"thực dân pháp|yên bái|côn đảo|sơn la|prison|prisión|cárcel|alcantarillado|almendro|tap code|"
            r"american|pow|断头台|火炉|狱|监狱|刑務所|モモタマナ|ギロチン|感化|"
            r"chế độ giam|cai ngục|bát sắt|lập là|cơm hẩm|vượt ngục|báo chí trong tù|audioguide|"
            r"giá vé|mở cửa|gửi xe|xe lăn|trống đồng|đại hồng chung|bảo kiếm|hiện vật",
            q,
        ))
        if domain_hit:
            return False
        if re.search(r"(\b(?:python|javascript|sql|react|source code|write code|viết code|debug|bitcoin|crypto|weather|thời tiết|chứng khoán|toán học|phương trình|giải bài tập|sort a list)\b|\d+\s*[\+\-\*\/]\s*\d+\s*=)", q):
            return True
        if max(zone_scores.values(), default=0.0) >= 1.5 or best_qa_score >= 0.32:
            return False
        return False

    def retrieve(
        self,
        question: str,
        language: str = "auto",
        zone_hint: str = "",
        beacon_code: str = "",
        top_k: int = 5,
        translated_vi: str | None = None,
        artifact_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pre = preprocess_question(question, language=language, translated_vi_text=translated_vi)
        detected_lang = pre["detected_language"]
        original_lang = pre["original_language"]
        target_lang = pre["target_language"]
        is_injection = pre["is_prompt_injection"]
        audience = pre["audience"]
        is_deictic = pre["is_deictic_exhibit"]
        has_vi_pivot = bool(translated_vi and translated_vi.strip()) or detected_lang == "vi"

        # Primary working query on the Vietnamese core (native normalized VI or translated VI)
        vi_working_q = pre["normalized_vi_query"] if has_vi_pivot else question
        intent = classify_intent(f"{question} {vi_working_q}" if translated_vi else vi_working_q)

        orig_norm = _norm(question)
        vi_norm = _norm(vi_working_q)
        orig_tokens = set(_tokenize(question))
        vi_tokens = set(_tokenize(vi_working_q))
        q_tokens = orig_tokens | vi_tokens
        q_tri = _char_trigrams(vi_working_q if has_vi_pivot else question)
        q_tri_norm = _tri_norm(q_tri)

        # 1. Cross-lingual concept aliases & Vietnamese expansion (checked on both original & VI pivot)
        zone_scores: dict[str, float] = {z["zone_id"]: 0.0 for z in self.zones}
        expanded_terms: list[str] = []
        matched_concept_labels: list[str] = []
        combined_norm = f"{orig_norm} {vi_norm}" if vi_norm != orig_norm else orig_norm
        concept_matched_any = False
        for pattern, z_list, vi_terms in _CONCEPT_ALIASES:
            if re.search(pattern, combined_norm):
                concept_matched_any = True
                for zid in z_list:
                    zone_scores[zid] = zone_scores.get(zid, 0.0) + 3.0
                expanded_terms.extend(vi_terms)
                matched_concept_labels.extend(vi_terms[:4])

        if zone_hint:
            zh_norm = _norm(zone_hint)
            for z in self.zones:
                if z["zone_id"].lower() == zh_norm or any(zh_norm in _norm(v) for v in z["names"].values()):
                    zone_scores[z["zone_id"]] += 4.0

        has_hoa_lo_topic = concept_matched_any or bool(re.search(r"hỏa lò|hoa lo|maison centrale", combined_norm))
        use_beacon_exhibit, beacon_zids = _evaluate_beacon_binding(artifact_context, combined_norm, is_deictic, has_hoa_lo_topic)

        # Apply keyword disambiguation matrix from dataset_hoa_lo_vi to separate colliding concepts cleanly
        disambig_matched: list[str] = []
        for cluster in self.disambiguation_rules:
            triggers = [t.strip().lower() for t in cluster.get("trigger_keyword", "").split("/") if t.strip()]
            if any(re.search(rf"\b{re.escape(tr)}\b", combined_norm) for tr in triggers):
                for route in cluster.get("routes", []):
                    co_hits = sum(1 for kw in route.get("if_cooccurs", []) if _norm(kw) in combined_norm)
                    if co_hits >= 1:
                        tz = route.get("target_zone", "")
                        if tz in zone_scores:
                            zone_scores[tz] += 4.5 + min(2.0, 0.8 * (co_hits - 1))
                        expanded_terms.extend(_tokenize(route.get("intent", "")))
                        disambig_matched.append(f"{tz}:{route.get('intent', '')}")
                        break

        effective_code = str((artifact_context or {}).get("code") or beacon_code or "").strip()
        if effective_code in _BEACON_TO_ZONES and (use_beacon_exhibit or not has_hoa_lo_topic):
            for zid in _BEACON_TO_ZONES[effective_code]:
                zone_scores[zid] += 2.0
        for zid in beacon_zids:
            zone_scores[zid] += 8.0 if use_beacon_exhibit else 2.5
        if use_beacon_exhibit and artifact_context:
            art_title = str(artifact_context.get("artifact_name") or artifact_context.get("name") or "")
            art_loc = str(artifact_context.get("location") or "")
            beacon_tokens = _tokenize(f"{art_title} {art_loc}")
            expanded_terms.extend(beacon_tokens)
            vi_tokens = vi_tokens | set(beacon_tokens)
            q_tokens = q_tokens | set(beacon_tokens)

        # 2. Match against 1,600 extended questions (in detected_lang AND Vietnamese Bo1/Bo2 when VI pivot is available)
        ext_scored: list[tuple[float, dict[str, Any]]] = []
        orig_len = max(1, len(orig_tokens))
        vi_len = max(1, len(vi_tokens))
        orig_tri = _char_trigrams(question)
        orig_tri_norm = _tri_norm(orig_tri)
        for ex in self.extended_q:
            ex_lang = ex["language"]
            if has_vi_pivot and ex_lang == "vi":
                cmp_tokens = vi_tokens
                cmp_len = vi_len
                cmp_tri = q_tri
                cmp_tri_norm = q_tri_norm
            elif ex_lang == detected_lang:
                cmp_tokens = orig_tokens
                cmp_len = orig_len
                cmp_tri = orig_tri
                cmp_tri_norm = orig_tri_norm
            else:
                continue

            tok_overlap = len(cmp_tokens & ex["_tokens"]) / cmp_len if cmp_tokens else 0.0
            if tok_overlap < 0.08 and ex_lang not in ("zh", "ja"):
                continue
            tri_sim = _cosine(cmp_tri, cmp_tri_norm, ex["_tri"], ex["_tri_norm"])
            sc = 0.65 * tok_overlap + 0.35 * tri_sim + 0.08
            if sc > 0.25:
                ext_scored.append((sc, ex))

        ext_scored.sort(key=lambda x: -x[0])
        matched_ext = [x[1] for x in ext_scored[:3]]
        pinned_weights: dict[str, float] = {}
        prelinked_warning_ids: list[str] = []
        for rank, (sc, ex) in enumerate(ext_scored[:3]):
            zone_scores[ex["zone_id"]] = zone_scores.get(ex["zone_id"], 0.0) + sc * 4.5
            if ex.get("golden_ref_id"):
                w = 1.0 if rank == 0 else (0.55 if sc >= 0.35 else 0.35)
                pinned_weights[ex["golden_ref_id"]] = max(pinned_weights.get(ex["golden_ref_id"], 0.0), w)
            # Pull pre-linked top-3 Golden Q&A IDs from Bo 2 / 4-Lang extractions
            if rank == 0 and sc >= 0.32:
                for rel_idx, rel_id in enumerate(ex.get("related_golden_qa_ids", [])[:3]):
                    rel_w = max(0.35, 0.85 - rel_idx * 0.22)
                    pinned_weights[rel_id] = max(pinned_weights.get(rel_id, 0.0), rel_w)
                prelinked_warning_ids.extend(ex.get("audit_warning_ids", []))
            # Expand with Vietnamese zone name + artifact tokens
            z_vi_name = self.zones_by_id[ex["zone_id"]]["names"]["vi"]
            expanded_terms.extend(_tokenize(f"{z_vi_name} {ex['artifact']}"))

        # 3. Zone keyword match
        for z in self.zones:
            z_kws = set(z["keywords"])
            overlap = len((q_tokens | set(expanded_terms)) & z_kws)
            zone_scores[z["zone_id"]] += overlap * 0.25

        best_zone_id = max(zone_scores.items(), key=lambda kv: kv[1])[0]
        if zone_scores[best_zone_id] == 0.0:
            best_zone_id = "Z01"

        # Enrich offline normalized_vi_query with zone + artifact + concept terms if non-VI offline call
        if not has_vi_pivot:
            offline_terms = matched_concept_labels[:]
            if matched_ext:
                offline_terms.append(matched_ext[0].get("artifact", ""))
                top_rel_ids = matched_ext[0].get("related_golden_qa_ids", [])
                if top_rel_ids and top_rel_ids[0] in self.qa_by_id:
                    offline_terms.append(self.qa_by_id[top_rel_ids[0]]["artifact"])
            pre = preprocess_question(
                question,
                language=language,
                concept_terms_vi=offline_terms,
                zone_vi_hint=self.zones_by_id[best_zone_id]["names"]["vi"],
            )

        # 4. Retrieve Top-K Golden Q&A from kb_golden_qa.json (always grounded on Vietnamese core!)
        expanded_tokens = q_tokens | set(expanded_terms)
        exp_len = max(1, len(expanded_tokens))
        qa_scored: list[tuple[float, dict[str, Any]]] = []
        for item in self.golden_qa:
            all_ov = len(expanded_tokens & item["_tokens"]) / exp_len if expanded_tokens else 0.0
            q_ov = len(expanded_tokens & item["_q_tokens"]) / max(1, len(item["_q_tokens"])) if item["_q_tokens"] else 0.0
            tri_sim = _cosine(q_tri, q_tri_norm, item["_tri"], item["_tri_norm"]) if (has_vi_pivot and (all_ov > 0 or item["zone_id"] == best_zone_id)) else 0.0
            zone_bonus = 0.22 if item["zone_id"] == best_zone_id else (0.08 if zone_scores.get(item["zone_id"], 0.0) >= 2.0 else 0.0)
            pin_bonus = pinned_weights.get(item["id"], 0.0)
            score = pin_bonus + 0.45 * all_ov + 0.30 * q_ov + 0.25 * tri_sim + zone_bonus
            qa_scored.append((score, item))

        qa_scored.sort(key=lambda x: -x[0])
        top_qa = [
            {
                "id": it["id"],
                "zone_id": it["zone_id"],
                "zone_vi": it["zone_vi"],
                "artifact": it["artifact"],
                "question": it["question"],
                "answer": it["answer"],
                "tone_level": it.get("tone_level", ""),
                "fact_card_ids": it.get("fact_card_ids", []),
                "story_ids": it.get("story_ids", []),
                "score": round(sc, 3),
            }
            for sc, it in qa_scored[:top_k]
        ]

        # 5. Select relevant Golden Facts, Fact Cards, Myth-Busters, Micro-Stories & Audit Warnings
        disambig_zones = {d.split(":", 1)[0] for d in disambig_matched if ":" in d}
        selected_zones = {best_zone_id} | {it["zone_id"] for it in top_qa[:2]} | disambig_zones
        relevant_facts = [
            gf for gf in self.golden_facts
            if (set(gf["zone_ids"]) & selected_zones) or gf["id"] in ("GF-01", "GF-03")
        ]

        picked_card_ids: list[str] = []
        for it in top_qa[:2]:
            for cid in it.get("fact_card_ids", []):
                if cid not in picked_card_ids:
                    picked_card_ids.append(cid)
        if not picked_card_ids:
            picked_card_ids = list(self.zones_by_id[best_zone_id].get("fact_card_ids", [])[:2])
        fact_cards = [self.fact_cards_by_id[cid] for cid in picked_card_ids[:3] if cid in self.fact_cards_by_id]

        matched_myths: list[dict[str, Any]] = []
        mb_tokens_q = expanded_tokens
        for mb in self.myth_busters:
            if mb.get("zone_id") in selected_zones and len(mb_tokens_q & mb.get("_tokens", set())) >= 2:
                matched_myths.append({
                    "myth_id": mb["myth_id"],
                    "common_misconception": mb["common_misconception"],
                    "truth": mb["truth"],
                    "tactful_correction_vi": mb["tactful_correction_vi"],
                })

        picked_story_ids: list[str] = []
        for it in top_qa[:2]:
            for sid in it.get("story_ids", []):
                if sid not in picked_story_ids:
                    picked_story_ids.append(sid)
        micro_stories = [self.stories_by_id[sid] for sid in picked_story_ids[:2] if sid in self.stories_by_id]

        zone_tone_level = (
            (top_qa[0].get("tone_level") if top_qa else "")
            or self.zones_by_id[best_zone_id].get("tone_level", "")
        )

        selected_warning_ids: list[str] = []
        for wid in prelinked_warning_ids:
            if wid not in selected_warning_ids:
                selected_warning_ids.append(wid)
        for rule in self.pitfall_rules:
            rid = rule["rule_id"]
            if rid in selected_warning_ids:
                continue
            if rid == "AP-06":
                if intent != "yes_no":
                    selected_warning_ids.append(rid)
                continue
            zone_hit = bool(set(rule["zone_ids"]) & selected_zones)
            kw_hit = any(kw in combined_norm for kw in rule["trigger_keywords"])
            if kw_hit or (zone_hit and rule["severity"] == "P0"):
                selected_warning_ids.append(rid)

        audit_warnings = [
            {
                "rule_id": self.pitfall_rules_by_id[rid]["rule_id"],
                "severity": self.pitfall_rules_by_id[rid]["severity"],
                "pitfall": self.pitfall_rules_by_id[rid]["pitfall"],
                "guard_instruction": self.pitfall_rules_by_id[rid]["guard_instruction"],
            }
            for rid in selected_warning_ids
            if rid in self.pitfall_rules_by_id
        ]

        best_qa_score = qa_scored[0][0] if qa_scored else 0.0
        out_of_scope = self.is_obviously_out_of_scope(
            f"{question} {vi_working_q}",
            zone_scores,
            best_qa_score,
            is_injection=is_injection,
            use_beacon_exhibit=use_beacon_exhibit,
        )
        web_intent = map_to_web_intent(intent, best_zone_id, combined_norm, out_of_scope, is_injection, use_beacon_exhibit)

        return {
            "original_question": pre["original_question"],
            "original_language": original_lang,
            "detected_language": detected_lang,
            "target_language": target_lang,
            "normalized_vi_query": pre["normalized_vi_query"],
            "pivot_method": pre["pivot_method"],
            "normalization_notes": pre["normalization_notes"],
            "is_prompt_injection": is_injection,
            "audience": audience,
            "is_deictic_exhibit": is_deictic,
            "use_beacon_exhibit_primary": use_beacon_exhibit,
            "active_artifact": artifact_context if (use_beacon_exhibit or effective_code == "002") else None,
            "intent": intent,
            "web_intent": web_intent,
            "zone_id": best_zone_id,
            "zone_names": self.zones_by_id[best_zone_id]["names"],
            "zone_audit_baseline": self.audit_baselines_by_zone.get(best_zone_id, {}),
            "is_likely_out_of_scope": out_of_scope,
            "tone_level": zone_tone_level,
            "golden_facts": relevant_facts,
            "fact_cards": fact_cards,
            "myth_busters": matched_myths[:2],
            "micro_stories": micro_stories,
            "audit_warnings": audit_warnings,
            "disambiguation_matched": disambig_matched,
            "top_qa": top_qa,
            "matched_extended": [
                {
                    "id": m["id"],
                    "dataset": m["dataset"],
                    "zone_id": m["zone_id"],
                    "artifact": m["artifact"],
                    "related_golden_qa_ids": m.get("related_golden_qa_ids", []),
                    "audit_warning_ids": m.get("audit_warning_ids", []),
                }
                for m in matched_ext
            ],
        }
