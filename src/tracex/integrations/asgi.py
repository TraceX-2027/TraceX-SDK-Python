from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Iterable, MutableMapping, Optional, Tuple

from tracex.client import Client, Hub

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _extract_headers(raw_headers: Optional[Iterable[Tuple[bytes, bytes]]]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not raw_headers:
        return headers
    for k, v in raw_headers:
        try:
            key = k.decode("latin-1").lower()
            val = v.decode("latin-1")
            headers[key] = val
        except Exception:
            continue
    return headers


class TraceXASGIMiddleware:
    """ASGI middleware for FastAPI and Starlette applications."""

    def __init__(self, app: ASGIApp, client: Optional[Client] = None) -> None:
        self.app = app
        self._explicit_client = client

    def _resolve_client(self) -> Optional[Client]:
        return self._explicit_client if self._explicit_client is not None else Hub.current().client

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        query_bytes = scope.get("query_string", b"")
        query_string = (
            query_bytes.decode("latin-1", errors="replace")
            if isinstance(query_bytes, (bytes, bytearray))
            else str(query_bytes or "")
        )
        headers = _extract_headers(scope.get("headers"))
        request_context: Dict[str, Any] = {
            "method": method,
            "path": path,
            "query_string": query_string,
            "headers": headers,
        }

        status_code = 500
        start_time = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            active_client = self._resolve_client()
            if active_client is not None:
                try:
                    active_client.add_breadcrumb(
                        message=f"{method} {path} -> 500",
                        category="network.http",
                        level="error",
                        data={
                            "method": method,
                            "path": path,
                            "status": 500,
                            "duration_ms": duration_ms,
                        },
                    )
                    active_client.capture_exception(
                        exc,
                        extra_context={"request": request_context},
                    )
                except Exception:
                    pass
            raise
        else:
            duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            active_client = self._resolve_client()
            if active_client is not None:
                try:
                    level = "error" if status_code >= 500 else ("warning" if status_code >= 400 else "info")
                    active_client.add_breadcrumb(
                        message=f"{method} {path} -> {status_code}",
                        category="network.http",
                        level=level,
                        data={
                            "method": method,
                            "path": path,
                            "status": status_code,
                            "duration_ms": duration_ms,
                        },
                    )
                except Exception:
                    pass