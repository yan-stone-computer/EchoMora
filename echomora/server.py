from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .engine import EchoMora


DEMO_DIR = Path(__file__).resolve().parent / "demo"
IDENTIFIER = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def _identifier(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 64 or any(char not in IDENTIFIER for char in text):
        raise ValueError(f"{field} 必须是 1-64 位字母、数字、下划线或连字符")
    return text


class EchoMoraHandler(BaseHTTPRequestHandler):
    server_version = "EchoMora/0.1"

    @property
    def engine(self) -> EchoMora:
        return self.server.engine  # type: ignore[attr-defined]

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 32_000:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("请求体必须是 JSON object")
        return value

    def _serve_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/"):
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, self.engine.health())
            return
        if parsed.path == "/api/snapshot":
            try:
                query = parse_qs(parsed.query)
                group_id = _identifier(query.get("group_id", ["demo"])[0], "group_id")
                user_id = _identifier(query.get("user_id", ["u_alice"])[0], "user_id")
                self._json(
                    HTTPStatus.OK,
                    self.engine.snapshot(group_id, user_id),
                )
            except Exception as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        relative = parsed.path.lstrip("/") or "index.html"
        candidate = (DEMO_DIR / relative).resolve()
        if DEMO_DIR.resolve() not in candidate.parents and candidate != DEMO_DIR.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._serve_file(candidate)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            group_id = _identifier(payload.get("group_id", "demo"), "group_id")
            user_id = _identifier(payload.get("user_id", "u_alice"), "user_id")
            if parsed.path == "/api/chat":
                user_name = str(payload.get("user_name", "小岚"))[:30]
                content = str(payload.get("content", ""))
                use_llm = bool(payload.get("use_llm", True))
                result = self.engine.chat(
                    group_id, user_id, user_name, content, use_llm=use_llm
                )
                self._json(HTTPStatus.OK, result)
                return
            if parsed.path == "/api/sleep":
                self._json(HTTPStatus.OK, self.engine.sleep(group_id))
                return
            if parsed.path == "/api/reset":
                self.engine.reset(group_id)
                self._json(HTTPStatus.OK, {"ok": True})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def serve(engine: EchoMora, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), EchoMoraHandler)
    server.engine = engine  # type: ignore[attr-defined]
    print(f"EchoMora is running at http://{host}:{port}")
    print(f"LLM mode: {'DeepSeek' if engine.deepseek.enabled else 'offline demo'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

