from __future__ import annotations

import asyncio
from typing import Any, Iterable, List, MutableMapping, Tuple

import pytest

import tracex
from tracex.client import Hub
from tracex.integrations.asgi import TraceXASGIMiddleware
from tracex.integrations.wsgi import TraceXWSGIMiddleware


def test_asgi_middleware_logs_breadcrumb_and_traps_route_exception() -> None:
    Hub.current().reset()
    client = tracex.init(project_key="proj_asgi", install_hooks=False)

    async def sample_asgi_app(scope: Any, receive: Any, send: Any) -> None:
        if scope["path"] == "/ok":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
            return
        raise RuntimeError("boom in fastapi route password=SecretRoutePass")

    app = TraceXASGIMiddleware(sample_asgi_app)

    async def run_requests() -> None:
        async def dummy_receive() -> MutableMapping[str, Any]:
            return {"type": "http.request"}

        async def dummy_send(msg: MutableMapping[str, Any]) -> None:
            pass

        await app(
            {"type": "http", "method": "GET", "path": "/ok", "headers": []},
            dummy_receive,
            dummy_send,
        )

        with pytest.raises(RuntimeError, match="boom in fastapi route"):
            await app(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/crash",
                    "headers": [(b"authorization", b"Bearer top_secret_jwt_123")],
                },
                dummy_receive,
                dummy_send,
            )

    asyncio.run(run_requests())

    crumbs = client.breadcrumbs.snapshot()
    assert len(crumbs) == 2
    assert crumbs[0]["category"] == "network.http"
    assert crumbs[0]["data"]["status"] == 200
    assert crumbs[1]["data"]["status"] == 500

    assert len(client.captured_events) == 1
    event = client.captured_events[0]
    assert "SecretRoutePass" not in event["error_message"]
    assert "top_secret_jwt_123" not in event["context"]["request"]["headers"]["authorization"]
    Hub.current().reset()


def test_wsgi_middleware_logs_breadcrumb_and_traps_route_exception() -> None:
    Hub.current().reset()
    client = tracex.init(project_key="proj_wsgi", install_hooks=False)

    def sample_wsgi_app(environ: Any, start_response: Any) -> Iterable[bytes]:
        if environ.get("PATH_INFO") == "/health":
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"healthy"]
        raise ValueError("flask endpoint crash")

    app = TraceXWSGIMiddleware(sample_wsgi_app)

    def dummy_start_response(status: str, headers: List[Tuple[str, str]], exc_info: Any = None) -> None:
        pass

    list(app({"REQUEST_METHOD": "GET", "PATH_INFO": "/health"}, dummy_start_response))

    with pytest.raises(ValueError, match="flask endpoint crash"):
        app(
            {
                "REQUEST_METHOD": "DELETE",
                "PATH_INFO": "/items/9",
                "HTTP_AUTHORIZATION": "Bearer wsgi_secret_token",
            },
            dummy_start_response,
        )

    assert len(client.breadcrumbs) == 2
    assert len(client.captured_events) == 1
    assert "wsgi_secret_token" not in client.captured_events[0]["context"]["request"]["headers"]["authorization"]
    Hub.current().reset()