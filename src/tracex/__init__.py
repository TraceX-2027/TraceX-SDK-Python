from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from tracex.breadcrumbs import Breadcrumb, BreadcrumbBuffer
from tracex.client import Client, DEFAULT_ENDPOINT, Hub
from tracex.integrations.asgi import TraceXASGIMiddleware
from tracex.integrations.wsgi import TraceXWSGIMiddleware
from tracex.scrubber import PIIScrubber

__version__ = "1.0.0"
__all__ = [
    "init",
    "capture_exception",
    "add_breadcrumb",
    "attach_asyncio_loop",
    "Client",
    "Hub",
    "Breadcrumb",
    "BreadcrumbBuffer",
    "PIIScrubber",
    "TraceXASGIMiddleware",
    "TraceXWSGIMiddleware",
    "__version__",
]


def init(
    project_key: str,
    endpoint: str = DEFAULT_ENDPOINT,
    environment: str = "production",
    app_version: str = "1.0.0",
    max_breadcrumbs: int = 50,
    install_hooks: bool = True,
) -> Client:
    if not project_key or not project_key.strip():
        raise ValueError("project_key must be a non-empty string")
    if max_breadcrumbs < 0:
        raise ValueError("max_breadcrumbs must be non-negative")

    Hub.current().reset()
    client = Client(
        project_key=project_key,
        endpoint=endpoint,
        environment=environment,
        app_version=app_version,
        max_breadcrumbs=max_breadcrumbs,
        install_hooks=install_hooks,
    )
    Hub.current().bind_client(client)
    return client


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
) -> Optional[Breadcrumb]:
    return Hub.current().add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data,
    )


def capture_exception(
    exception: Optional[BaseException] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    return Hub.current().capture_exception(exception, extra_context=extra_context)


def attach_asyncio_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    Hub.current().attach_asyncio_loop(loop)