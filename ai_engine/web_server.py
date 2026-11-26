"""Standalone HTTP Server exposing HoaLoWebAdapter at `/api/chat/ask` (port 4001).

Point the Node.js Web Gateway (`AI_API_URL=http://127.0.0.1:4001/api/chat/ask`)
to this server to power Web & ESP32 Voice Hub queries independently.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Mapping
from urllib.parse import urlparse

try:
    from .web_adapter import HoaLoWebAdapter
except ImportError:
    from web_adapter import HoaLoWebAdapter

MAX_PAYLOAD_BYTES = 32 * 1024  # Match Web gateway 32KB limit


def _ci_header(headers: Mapping[str, str], name: str) -> str:
    low = name.lower()
    for k, v in headers.items():
        if k.lower() == low:
            return str(v)
    return ""


def dispatch_http_request(
    method: str,
    raw_path: str,
    headers: Mapping[str, str],
    raw_body: bytes,
    adapter: HoaLoWebAdapter,
    api_key_guard: str = "",
    server_port: int = 4001,
    start_ts: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """Route and process HTTP requests for /health, /stats, /api/chat/ask, and /api/hub/ask."""
    started = start_ts if start_ts is not None else time.time()
    m = method.upper()

    if m == "OPTIONS":
        return 200, {"ok": True}

    if api_key_guard:
        x_key = _ci_header(headers, "x-api-key")
        auth = _ci_header(headers, "authorization")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if x_key != api_key_guard and bearer != api_key_guard:
            return 401, {"success": False, "error": "Unauthorized: invalid or missing API Key."}

    path = urlparse(raw_path).path

    if m == "GET":
        if path in ("/health", "/api/health"):
            r = adapter.skill.retriever
            return 200, {
                "status": "UP",
                "version": "2.2.0 (Vietnamese-Pivot Web Adapter + dataset_hoa_lo_vi)",
                "port": server_port,
                "uptimeSeconds": round(time.time() - started, 2),
                "activeSessions": adapter.sessions.count(),
                "kb_stats": {
                    "zones": len(r.zones),
                    "golden_qa": len(r.golden_qa),
                    "extended_questions": len(r.extended_q),
                    "audit_records": r.audit_records_count,
                    "fact_cards": len(r.fact_cards),
                    "micro_stories": len(r.micro_stories),
                    "myth_busters": len(r.myth_busters),
                    "disambiguation_rules": len(r.disambiguation_rules),
                },
            }
        if path in ("/stats", "/api/stats"):
            snap = adapter.stats_snapshot()
            snap["uptimeSeconds"] = round(time.time() - started, 2)
            return 200, snap
        return 404, {"success": False, "error": f"Endpoint not found: {path}"}

    if m == "POST":
        if path not in ("/api/chat/ask", "/api/hub/ask", "/api/voice-query", "/api/translate", "/api/feedback"):
            return 404, {"success": False, "error": f"Endpoint not found: {path}"}
        if len(raw_body) > MAX_PAYLOAD_BYTES:
            return 413, {"success": False, "error": "Payload exceeds 32KB limit."}
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body.strip() else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 400, {"success": False, "error": "Invalid JSON body."}
        if not isinstance(payload, dict):
            return 400, {"success": False, "error": "JSON body must be an object."}

        if path == "/api/translate":
            return 200, adapter.handle_translate_request(payload)
        if path == "/api/feedback":
            return 200, adapter.handle_feedback_request(payload)

        if "language" not in payload and _ci_header(headers, "x-language"):
            payload["language"] = _ci_header(headers, "x-language")
        if "sessionId" not in payload and _ci_header(headers, "x-session-id"):
            payload["sessionId"] = _ci_header(headers, "x-session-id")
        if "code" not in payload and _ci_header(headers, "x-artifact-code"):
            payload["code"] = _ci_header(headers, "x-artifact-code")

        result = adapter.handle_chat_request(payload)
        if path in ("/api/hub/ask", "/api/voice-query"):
            d = result["data"]
            result = {
                "success": True,
                "status": "success",
                "question": d["originalQuestion"],
                "reply_text": d["reply"],
                "ai_source": d["provider"],
                "locked_language": d["language"],
                "data": d,
            }
        return 200, result

    return 405, {"success": False, "error": f"Method not allowed: {m}"}


def create_web_server(
    host: str = "127.0.0.1",
    port: int = 4001,
    adapter: HoaLoWebAdapter | None = None,
    api_key_guard: str = "",
) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer exposing /api/chat/ask, /api/hub/ask, /health, /stats."""
    active_adapter = adapter or HoaLoWebAdapter()
    start_ts = time.time()

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send_json(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, X-API-Key, X-Language, X-Artifact-Code, X-Session-Id",
            )
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self, method: str) -> None:
            try:
                content_len = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                content_len = 0
            if content_len > MAX_PAYLOAD_BYTES:
                self._send_json(413, {"success": False, "error": "Payload exceeds 32KB limit."})
                return
            raw_body = self.rfile.read(content_len) if content_len > 0 else b""
            status, body = dispatch_http_request(
                method=method,
                raw_path=self.path,
                headers=self.headers,
                raw_body=raw_body,
                adapter=active_adapter,
                api_key_guard=api_key_guard,
                server_port=self.server.server_port,
                start_ts=start_ts,
            )
            self._send_json(status, body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._handle("OPTIONS")

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return ThreadingHTTPServer((host, port), _Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Hỏa Lò Skill Web API Server (port 4001)")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "4001")))
    args = parser.parse_args()

    srv = create_web_server(host=args.host, port=args.port, api_key_guard=os.environ.get("API_KEY", ""))
    print(f"HoaLoGroqSkill Web Server listening on http://{args.host}:{srv.server_port}/api/chat/ask")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
