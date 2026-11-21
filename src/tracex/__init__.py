from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from tracex.client import Client, DEFAULT_ENDPOINT, Hub

__version__ = "1.0.0"
__all__ = [
    "init",
    "capture_exception",
    "attach_asyncio_loop",
    "Client",
    "Hub",
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


def capture_exception(exception: Optional[BaseException] = None) -> Optional[Dict[str, Any]]:
    return Hub.current().capture_exception(exception)


def attach_asyncio_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    Hub.current().attach_asyncio_loop(loop)