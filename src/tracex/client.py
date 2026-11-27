from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import sys
import threading
from types import TracebackType
from typing import Any, Deque, Dict, List, Optional, Type

from tracex.breadcrumbs import Breadcrumb, BreadcrumbBuffer, DEFAULT_MAX_BREADCRUMBS
from tracex.environment import collect_environment
from tracex.hooks import GlobalHookManager
from tracex.scrubber import PIIScrubber
from tracex.stacktrace import normalize_exception

DEFAULT_ENDPOINT = "https://tracex-edge-ingest.kareemadel10110.workers.dev/api/v1/crashes"
MAX_CAPTURED_EVENTS = 100


class Client:
    def __init__(
        self,
        project_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        environment: str = "production",
        app_version: str = "1.0.0",
        max_breadcrumbs: int = DEFAULT_MAX_BREADCRUMBS,
        install_hooks: bool = True,
    ) -> None:
        if not project_key or not project_key.strip():
            raise ValueError("project_key must be a non-empty string")
        if max_breadcrumbs < 0:
            raise ValueError("max_breadcrumbs must be non-negative")

        self.project_key = project_key.strip()
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.environment = environment or "production"
        self.app_version = app_version or "1.0.0"
        self.max_breadcrumbs = max_breadcrumbs
        self._install_hooks = install_hooks
        self._lock = threading.RLock()
        self._captured_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_CAPTURED_EVENTS)
        self._breadcrumbs = BreadcrumbBuffer(maxlen=max_breadcrumbs)
        self._scrubber = PIIScrubber()
        self._hook_manager = GlobalHookManager(self._capture_raw)

        if install_hooks:
            self._hook_manager.install()

    @property
    def captured_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._captured_events)

    @property
    def breadcrumbs(self) -> BreadcrumbBuffer:
        return self._breadcrumbs

    def add_breadcrumb(
        self,
        message: str,
        category: str = "custom",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> Breadcrumb:
        scrubbed_message = self._scrubber.scrub_text(message)
        scrubbed_data = self._scrubber.scrub_dict(data) if data else None
        return self._breadcrumbs.add(
            message=scrubbed_message,
            category=category,
            level=level,
            data=scrubbed_data,
        )

    def attach_asyncio_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._hook_manager.attach_asyncio_loop(loop)

    def build_crash_payload(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        exc_tb: Optional[TracebackType],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        exc_dto = normalize_exception(exc_type, exc_value, exc_tb)
        env_dto = collect_environment(
            app_version=self.app_version,
            environment_name=self.environment,
        )
        raw_breadcrumbs = self._breadcrumbs.snapshot()
        scrubbed_breadcrumbs = [self._scrubber.scrub_dict(b) for b in raw_breadcrumbs]

        payload: Dict[str, Any] = {
            "project_key": self.project_key,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "platform": "python",
            "language": "python",
            "exception_type": exc_dto.error_type,
            "error_message": self._scrubber.scrub_text(exc_dto.message),
            "stack_trace": self._scrubber.scrub_text(exc_dto.format_stack_trace()),
            "environment": env_dto.to_dict(),
            "breadcrumbs": scrubbed_breadcrumbs,
        }
        if extra_context:
            payload["context"] = self._scrubber.scrub_dict(extra_context)
        return payload

    def capture_exception(
        self,
        exception: Optional[BaseException] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self._install_hooks:
            self._hook_manager.attach_asyncio_loop()
        if exception is not None:
            return self._capture_raw(
                type(exception),
                exception,
                exception.__traceback__,
                extra_context=extra_context,
            )

        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_type is None and exc_value is None:
            return None
        return self._capture_raw(exc_type, exc_value, exc_tb, extra_context=extra_context)

    def _capture_raw(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        exc_tb: Optional[TracebackType],
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._install_hooks:
            self._hook_manager.attach_asyncio_loop()
        payload = self.build_crash_payload(exc_type, exc_value, exc_tb, extra_context=extra_context)
        with self._lock:
            self._captured_events.append(payload)
        return payload

    def close(self) -> None:
        self._hook_manager.uninstall()


class Hub:
    _instance: Optional[Hub] = None
    _class_lock = threading.RLock()

    def __init__(self) -> None:
        self._client: Optional[Client] = None
        self._lock = threading.RLock()

    @classmethod
    def current(cls) -> Hub:
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def client(self) -> Optional[Client]:
        with self._lock:
            return self._client

    def bind_client(self, client: Optional[Client]) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = client

    def add_breadcrumb(
        self,
        message: str,
        category: str = "custom",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Breadcrumb]:
        with self._lock:
            active = self._client
        if active is None:
            return None
        return active.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data,
        )

    def capture_exception(
        self,
        exception: Optional[BaseException] = None,
        extra_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            active = self._client
        if active is None:
            return None
        return active.capture_exception(exception, extra_context=extra_context)

    def attach_asyncio_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        with self._lock:
            active = self._client
        if active is not None:
            active.attach_asyncio_loop(loop)

    def reset(self) -> None:
        self.bind_client(None)