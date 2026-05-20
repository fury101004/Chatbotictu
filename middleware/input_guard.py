from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from typing import Awaitable, Callable
from urllib.parse import parse_qs

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class InputGuardMiddleware:
    """ASGI middleware for request IDs, size limits, and lightweight token throttling."""

    CHAT_PATHS = {"/chat", "/api/chat", "/api/v1/chat"}
    TOKEN_PATHS = {"/api/auth/token", "/api/v1/auth/token"}
    UPLOAD_PATHS = {"/upload", "/api/v1/upload"}

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_message_chars: int = 2000,
        max_upload_bytes: int = 10 * 1024 * 1024,
        token_limit: int = 20,
        token_window_seconds: int = 60,
    ) -> None:
        self.app = app
        self.max_message_chars = max_message_chars
        self.max_upload_bytes = max_upload_bytes
        self.token_limit = token_limit
        self.token_window_seconds = token_window_seconds
        self._token_requests: dict[str, list[float]] = defaultdict(list)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))

        if method == "POST" and path in self.TOKEN_PATHS and self._is_token_rate_limited(scope):
            await self._send_json(
                send,
                status_code=429,
                request_id=request_id,
                payload={"status": "error", "detail": "Too many token requests. Try again later."},
                headers={b"retry-after": b"60"},
            )
            return

        if method == "POST" and path in self.UPLOAD_PATHS and self._declared_upload_too_large(scope):
            await self._send_json(
                send,
                status_code=413,
                request_id=request_id,
                payload={"status": "error", "detail": "File upload is too large. Maximum size is 10MB."},
            )
            return

        guarded_receive = receive
        if method == "POST" and path in self.CHAT_PATHS:
            body = await self._read_body(receive)
            message = self._extract_message(scope, body)
            if message is not None and len(message) > self.max_message_chars:
                await self._send_json(
                    send,
                    status_code=400,
                    request_id=request_id,
                    payload={
                        "status": "error",
                        "detail": f"Message is too long. Maximum is {self.max_message_chars} characters.",
                    },
                )
                return
            guarded_receive = self._replay_body(body)

        await self.app(scope, guarded_receive, send_with_request_id)

    def _client_ip(self, scope: Scope) -> str:
        header_map = {key.lower(): value for key, value in scope.get("headers", [])}
        forwarded_for = header_map.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode("latin-1").split(",", 1)[0].strip()
        client = scope.get("client")
        if client:
            return str(client[0])
        return "unknown"

    def _is_token_rate_limited(self, scope: Scope) -> bool:
        now = time.monotonic()
        cutoff = now - self.token_window_seconds
        ip = self._client_ip(scope)
        recent = [timestamp for timestamp in self._token_requests[ip] if timestamp > cutoff]
        self._token_requests[ip] = recent
        if len(recent) >= self.token_limit:
            return True
        recent.append(now)
        return False

    def _declared_upload_too_large(self, scope: Scope) -> bool:
        header_map = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = header_map.get(b"content-length")
        if not raw_length:
            return False
        try:
            return int(raw_length.decode("latin-1")) > self.max_upload_bytes
        except ValueError:
            return False

    async def _read_body(self, receive: Receive) -> bytes:
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    def _replay_body(self, body: bytes) -> Callable[[], Awaitable[Message]]:
        consumed = False

        async def receive() -> Message:
            nonlocal consumed
            if consumed:
                return {"type": "http.request", "body": b"", "more_body": False}
            consumed = True
            return {"type": "http.request", "body": body, "more_body": False}

        return receive

    def _extract_message(self, scope: Scope, body: bytes) -> str | None:
        header_map = {key.lower(): value for key, value in scope.get("headers", [])}
        content_type = header_map.get(b"content-type", b"").decode("latin-1").lower()

        if "application/json" in content_type:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
            if isinstance(payload, dict) and "message" in payload:
                return str(payload.get("message") or "")
            return None

        if "application/x-www-form-urlencoded" in content_type:
            try:
                fields = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return None
            values = fields.get("message")
            return values[0] if values else None

        return None

    async def _send_json(
        self,
        send: Send,
        *,
        status_code: int,
        request_id: str,
        payload: dict,
        headers: dict[bytes, bytes] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        raw_headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"x-request-id", request_id.encode("ascii")),
        ]
        if headers:
            raw_headers.extend(headers.items())
        await send({"type": "http.response.start", "status": status_code, "headers": raw_headers})
        await send({"type": "http.response.body", "body": body})

