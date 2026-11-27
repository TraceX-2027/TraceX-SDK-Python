from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, MutableMapping, Optional, Tuple

from tracex.client import Client, Hub

WSGIEnviron = MutableMapping[str, Any]
StartResponse = Callable[..., Any]
WSGIApp = Callable[[WSGIEnviron, StartResponse], Iterable[bytes]]


def _extract_wsgi_headers(environ: WSGIEnviron) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, val in environ.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").lower()
            headers[header_name] = str(val)
        elif key in ("CONTENT_TYPE", "CONTENT_LENGTH") and val:
            headers[key.replace("_", "-").lower()] = str(val)
    return headers


class TraceXWSGIMiddleware:
    """WSGI adapter middleware for Flask and Django applications."""

    def __init__(self, app: WSGIApp, client: Optional[Client] = None) -> None:
        self.app = app
        self._explicit_client = client

    def _resolve_client(self) -> Optional[Client]:
        return self._explicit_client if self._explicit_client is not None else Hub.current().client

    def __call__(self, environ: WSGIEnviron, start_response: StartResponse) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        query_string = str(environ.get("QUERY_STRING", ""))
        headers = _extract_wsgi_headers(environ)
        request_context: Dict[str, Any] = {
            "method": method,
            "path": path,
            "query_string": query_string,
            "headers": headers,
        }

        status_code = 500
        start_time = time.perf_counter()

        def custom_start_response(
            status: str,
            response_headers: List[Tuple[str, str]],
            exc_info: Any = None,
        ) -> Any:
            nonlocal status_code
            try:
                status_code = int(status.split(" ", 1)[0])
            except (ValueError, IndexError):
                status_code = 500
            return start_response(status, response_headers, exc_info)

        try:
            response_iterable = self.app(environ, custom_start_response)
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
        return response_iterable