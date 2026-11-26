"""Independent Web Adapter bridging HoaLoGroqSkill to Smart Museum Web Gateway (/api/chat/ask).

Exposes the HTTP JSON schema consumed by the Node.js V4.0 Gateway (`AI_API_URL`)
with zero dependency on legacy JS prompts or removed knowledge bases.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .groq_skill import (
        DEFAULT_GROQ_MODEL,
        GROQ_LIGHT_MODELS,
        HoaLoGroqSkill,
        clean_text_for_web,
    )
    from .preprocessor import normalize_vietnamese_text
except ImportError:
    from groq_skill import (
        DEFAULT_GROQ_MODEL,
        GROQ_LIGHT_MODELS,
        HoaLoGroqSkill,
        clean_text_for_web,
    )
    from preprocessor import normalize_vietnamese_text

_FOLLOWUP_RE = re.compile(
    r"\b(?:nó|họ|ông ấy|bà ấy|người đó|cái đó|cái này|chỗ đó|nơi đó|thế còn|vậy còn|nặng bao nhiêu|cao bao nhiêu|ở đâu|khi nào|năm nào)\b",
    re.IGNORECASE,
)


class _SessionMemory:
    """Thread-safe isolated session conversation store (keeps last 4 turns per sessionId)."""

    def __init__(self, max_sessions: int = 500, ttl_sec: float = 1800.0) -> None:
        self._lock = threading.Lock()
        self._max = max_sessions
        self._ttl = ttl_sec
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def get_or_create(self, session_id: str | None) -> tuple[str, dict[str, Any]]:
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(session_id or ""))[:72]
        if not clean_id:
            clean_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._lock:
            stale = [k for k, v in self._sessions.items() if now - v["updated_at"] > self._ttl]
            for k in stale:
                self._sessions.pop(k, None)
            if clean_id in self._sessions:
                self._sessions.move_to_end(clean_id)
                rec = self._sessions[clean_id]
                rec["updated_at"] = now
                return clean_id, {
                    "history": list(rec["history"]),
                    "last_zone_id": rec.get("last_zone_id", ""),
                    "last_artifact": rec.get("last_artifact", ""),
                }
            rec = {"history": [], "last_zone_id": "", "last_artifact": "", "updated_at": now}
            self._sessions[clean_id] = rec
            if len(self._sessions) > self._max:
                self._sessions.popitem(last=False)
            return clean_id, {"history": [], "last_zone_id": "", "last_artifact": ""}

    def record_turn(self, session_id: str, question: str, reply: str, zone_id: str, artifact: str) -> None:
        now = time.time()
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                rec = {"history": [], "last_zone_id": "", "last_artifact": "", "updated_at": now}
                self._sessions[session_id] = rec
            rec["history"].extend([
                {"role": "user", "content": question[:300]},
                {"role": "assistant", "content": reply[:400]},
            ])
            rec["history"] = rec["history"][-6:]
            if zone_id:
                rec["last_zone_id"] = zone_id
            if artifact:
                rec["last_artifact"] = artifact
            rec["updated_at"] = now

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


class _LruResponseCache:
    """Thread-safe TTL cache for fast Web repeated queries."""

    def __init__(self, max_items: int = 400, ttl_sec: float = 600.0) -> None:
        self._lock = threading.Lock()
        self._max = max_items
        self._ttl = ttl_sec
        self._store: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock:
            item = self._store.get(key)
            if not item:
                self.misses += 1
                return None
            ts, data = item
            if now - ts > self._ttl:
                self._store.pop(key, None)
                self.misses += 1
                return None
            self._store.move_to_end(key)
            self.hits += 1
            return dict(data)

    def set(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._store[key] = (time.time(), dict(value))
            self._store.move_to_end(key)
            if len(self._store) > self._max:
                self._store.popitem(last=False)


class HoaLoWebAdapter:
    """Adapter exposing our independent Hỏa Lò skill over the Web `/api/chat/ask` contract."""

    PROVIDER_NAME = "HoaLoGroqSkill (Vietnamese-Pivot Hybrid RAG)"

    def __init__(
        self,
        skill: HoaLoGroqSkill | None = None,
        skill_dir: Path | None = None,
        feedback_log_path: Path | None = None,
    ) -> None:
        self.skill = skill if skill is not None else HoaLoGroqSkill(skill_dir=skill_dir)
        self.sessions = _SessionMemory()
        self.cache = _LruResponseCache()
        self.feedback_log_path = feedback_log_path or (self.skill.skill_dir / "knowledge" / "visitor_feedback.jsonl")
        self._feedback_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self.total_requests = 0
        self.groq_calls = 0
        self.fallback_calls = 0
        self.total_latency_ms = 0.0

    @staticmethod
    def _extract_question(payload: dict[str, Any]) -> str:
        for key in ("question", "voice_text", "text", "message", "query"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:500]
        return ""

    @staticmethod
    def _build_offline_grounded_reply(ctx: dict[str, Any], target_lang: str) -> str:
        """Synthesize a clean plain-text reply strictly from our own Golden Facts, Golden Q&A, or Beacon data."""
        if ctx.get("is_prompt_injection"):
            return clean_text_for_web(HoaLoGroqSkill._injection_refusal(target_lang))
        if ctx.get("is_likely_out_of_scope"):
            return clean_text_for_web(HoaLoGroqSkill._injection_refusal(target_lang))

        active_art = ctx.get("active_artifact")
        if active_art and ctx.get("use_beacon_exhibit_primary"):
            dlg = active_art.get("dialogue") or {}
            dlg_text = dlg.get("text") if isinstance(dlg, dict) else ""
            if dlg_text:
                return clean_text_for_web(dlg_text)

        top_qa = ctx.get("top_qa") or []
        gfs = ctx.get("golden_facts") or []
        zone_id = ctx.get("zone_id", "")
        zone_gfs = [gf for gf in gfs if zone_id in gf.get("zone_ids", [])]
        picked_gf = zone_gfs[0] if zone_gfs else (gfs[0] if gfs else None)

        if target_lang == "en" and picked_gf and picked_gf.get("fact_en"):
            return clean_text_for_web(picked_gf["fact_en"])
        if top_qa:
            return clean_text_for_web(top_qa[0]["answer"])
        if picked_gf:
            return clean_text_for_web(picked_gf.get("fact_vi") or picked_gf.get("fact_en", ""))

        return clean_text_for_web(
            "Di tích Lịch sử Nhà tù Hỏa Lò nằm tại số 1 phố Hỏa Lò, quận Hoàn Kiếm, Hà Nội, mở cửa tham quan hằng ngày từ 8 giờ đến 17 giờ."
        )

    def handle_chat_request(
        self,
        payload: dict[str, Any],
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Process one Web request compatible with POST /api/chat/ask and /api/hub/ask."""
        t0 = time.perf_counter()
        raw_question = self._extract_question(payload)
        language = str(payload.get("language") or payload.get("lang") or "auto").strip() or "auto"
        artifact_ctx = payload.get("artifactContext") or payload.get("artifact_context")
        if not isinstance(artifact_ctx, dict):
            code_only = str(payload.get("code") or "").strip()
            artifact_ctx = {"code": code_only} if code_only else None

        session_id_raw = payload.get("sessionId") or payload.get("session_id") or payload.get("device_id")
        session_id, sess_state = self.sessions.get_or_create(session_id_raw)
        pipeline_mode = str(payload.get("pipeline_mode") or "vietnamese_pivot")
        response_style = str(payload.get("response_style") or "web")
        model = str(payload.get("model") or DEFAULT_GROQ_MODEL)

        if not raw_question:
            return {
                "success": True,
                "data": {
                    "reply": "Quý khách vui lòng đặt câu hỏi về Di tích Lịch sử Nhà tù Hỏa Lò hoặc hiện vật trước mắt để tôi hỗ trợ chi tiết.",
                    "intent": "CLARIFICATION",
                    "provider": self.PROVIDER_NAME,
                    "latencyMs": 1,
                    "language": "vi" if language == "auto" else language.split("-")[0].lower(),
                    "sessionId": session_id,
                    "groundingStatus": "GROUNDED",
                    "confidence": "HIGH",
                    "confidenceScore": 1.0,
                    "requiresHuman": False,
                    "responseType": "CLARIFICATION",
                },
            }

        # Resolve short deictic follow-ups using active session topic
        norm_q_for_follow, _ = normalize_vietnamese_text(raw_question)
        is_followup = bool(sess_state["history"] and len(raw_question) <= 75 and _FOLLOWUP_RE.search(norm_q_for_follow))
        zone_hint = str(payload.get("zone_hint") or (sess_state["last_zone_id"] if is_followup else ""))

        art_code = str((artifact_ctx or {}).get("code") or "")
        cache_key = f"{norm_q_for_follow.lower()}|{language.lower()}|{art_code}|{response_style}"
        if not is_followup:
            cached = self.cache.get(cache_key)
            if cached:
                cached["sessionId"] = session_id
                cached["latencyMs"] = max(1, int((time.perf_counter() - t0) * 1000))
                cached["cached"] = True
                self.sessions.record_turn(session_id, raw_question, cached["reply"], cached.get("zoneId", ""), art_code)
                with self._stats_lock:
                    self.total_requests += 1
                    self.total_latency_ms += cached["latencyMs"]
                return {"success": True, "data": cached}

        eff_key = (api_key if api_key is not None else os.environ.get("GROQ_API_KEY") or "").strip()
        used_fallback = False
        try:
            if not eff_key:
                raise ValueError("OFFLINE_MODE")
            out = self.skill.ask_groq(
                question=raw_question,
                api_key=eff_key,
                model=model,
                language=language,
                zone_hint=zone_hint,
                beacon_code=art_code,
                pipeline_mode=pipeline_mode,
                response_style=response_style,
                artifact_context=artifact_ctx,
                conversation_history=sess_state["history"] if is_followup else None,
                preprocess_model=GROQ_LIGHT_MODELS[0],
                translate_model=GROQ_LIGHT_MODELS[0],
                timeout=4.5,
            )
            with self._stats_lock:
                self.groq_calls += 1
        except Exception:
            used_fallback = True
            _, ctx = self.skill.build_messages(
                question=raw_question,
                language=language,
                zone_hint=zone_hint,
                beacon_code=art_code,
                artifact_context=artifact_ctx,
                conversation_history=sess_state["history"] if is_followup else None,
                response_style=response_style,
            )
            target_lang = ctx["target_language"]
            vi_ans = self._build_offline_grounded_reply(ctx, "vi")
            reply_text = self._build_offline_grounded_reply(ctx, target_lang)
            out = {
                "reply_text": reply_text,
                "vietnamese_answer": vi_ans,
                "original_question": ctx["original_question"],
                "original_language": target_lang,
                "normalized_vi_query": ctx["normalized_vi_query"],
                "pivot_method": ctx["pivot_method"],
                "pipeline_mode": "offline_grounded_fallback",
                "response_style": response_style,
                "pipeline_stages": [{"stage": "offline_grounded_fallback", "latency_ms": 0.0}],
                "model": "offline-golden-kb",
                "language": target_lang,
                "zone_id": ctx["zone_id"],
                "zone_name": ctx["zone_names"].get(target_lang) or ctx["zone_names"].get("vi"),
                "intent": ctx["intent"],
                "web_intent": ctx["web_intent"],
                "retrieved_ids": [q["id"] for q in ctx["top_qa"]],
                "audit_warning_ids": [w["rule_id"] for w in ctx.get("audit_warnings", [])],
                "is_prompt_injection": ctx["is_prompt_injection"],
                "audience": ctx["audience"],
                "usage": {},
            }
            with self._stats_lock:
                self.fallback_calls += 1

        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
        sources = ["Ban Quản Lý Di Tích Nhà Tù Hỏa Lò"] + list(out.get("retrieved_ids", [])[:3])
        response_data = {
            "reply": out["reply_text"],
            "intent": out.get("web_intent") or "HISTORICAL_FACT",
            "queryIntent": out.get("intent", "open_fact"),
            "audience": out.get("audience", "general"),
            "provider": f"{self.PROVIDER_NAME} [{out['model']}]" if not used_fallback else f"{self.PROVIDER_NAME} [Offline Golden KB]",
            "latencyMs": latency_ms,
            "language": out["language"],
            "sessionId": session_id,
            "zoneId": out["zone_id"],
            "zoneName": out.get("zone_name", ""),
            "originalQuestion": out["original_question"],
            "normalizedViQuery": out["normalized_vi_query"],
            "vietnameseAnswer": out.get("vietnamese_answer", ""),
            "pivotMethod": out.get("pivot_method", ""),
            "pipelineMode": out.get("pipeline_mode", pipeline_mode),
            "pipelineStages": out.get("pipeline_stages", []),
            "retrievedIds": out.get("retrieved_ids", []),
            "auditWarningIds": out.get("audit_warning_ids", []),
            "sources": sources,
            "groundingStatus": "GROUNDED",
            "confidence": "HIGH",
            "confidenceScore": 0.96 if not used_fallback else 0.88,
            "isFollowUp": is_followup,
            "requiresHuman": False,
            "responseType": "DIRECT_ANSWER" if not used_fallback else "GROUNDED_KB_FALLBACK",
            "usage": out.get("usage") or {},
        }

        self.sessions.record_turn(session_id, raw_question, response_data["reply"], response_data["zoneId"], art_code)
        if not is_followup and not used_fallback:
            self.cache.set(cache_key, response_data)

        with self._stats_lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms

        return {"success": True, "data": response_data}

    def handle_translate_request(self, payload: dict[str, Any], api_key: str | None = None) -> dict[str, Any]:
        """Translate beacon text(s) into target language via Groq glossary-locked translator."""
        target_lang = str(payload.get("target_lang") or payload.get("language") or "vi").lower().strip().split("-")[0]
        if isinstance(payload.get("texts"), list):
            items = [str(x or "") for x in payload["texts"][:10]]
            translated_list = []
            for txt in items:
                tr_key = f"tr|{target_lang}|{txt[:180]}"
                hit = self.cache.get(tr_key)
                if hit:
                    translated_list.append(hit["text"])
                else:
                    res = self.skill.translate_text(txt, target_lang=target_lang, api_key=api_key)
                    if res.get("translated"):
                        self.cache.set(tr_key, res)
                    translated_list.append(res["text"])
            return {"success": True, "language": target_lang, "translations": translated_list}

        single = str(payload.get("text") or "")
        tr_key = f"tr|{target_lang}|{single[:180]}"
        hit = self.cache.get(tr_key)
        if hit:
            return {"success": True, **hit, "cached": True}
        res = self.skill.translate_text(single, target_lang=target_lang, api_key=api_key)
        if res.get("translated"):
            self.cache.set(tr_key, res)
        return {"success": True, **res}

    def handle_feedback_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist visitor rating & comment to an append-only audit JSONL log without altering verified KBs."""
        question = str(payload.get("question") or "").strip()[:500]
        reply = str(payload.get("reply") or "").strip()[:800]
        comment = str(payload.get("comment") or "").strip()[:300]
        rating = payload.get("rating")
        device_id = str(payload.get("device_id") or payload.get("deviceId") or "GUEST")[:64]
        language = str(payload.get("language") or "vi")[:12]
        if not question and not comment:
            return {"success": False, "error": "Missing question or comment in feedback payload."}
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "reply": reply,
            "rating": rating,
            "comment": comment,
            "device_id": device_id,
            "language": language,
        }
        with self._feedback_lock:
            self.feedback_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.feedback_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"success": True, "recorded": True, "entry": entry}

    def stats_snapshot(self) -> dict[str, Any]:
        with self._stats_lock:
            avg = round(self.total_latency_ms / self.total_requests, 2) if self.total_requests else 0.0
            return {
                "server": self.PROVIDER_NAME,
                "activeSessions": self.sessions.count(),
                "totalRequests": self.total_requests,
                "groqCalls": self.groq_calls,
                "fallbackCalls": self.fallback_calls,
                "averageLatencyMs": avg,
                "cacheStats": {"hits": self.cache.hits, "misses": self.cache.misses},
            }
