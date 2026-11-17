from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import sys
import threading
from types import TracebackType
from typing import Any, Deque, Dict, List, Optional, Type

from tracex.environment import collect_environment
from tracex.hooks import GlobalHookManager
from tracex.stacktrace import normalize_exception

DEFAULT_ENDPOINT = "https://api.tracex.io/api/v1/crashes"
MAX_CAPTURED_EVENTS = 100


class Client:
    def __init__(
        self,
        project_key: str,
        endpoint: str = DEFAULT_ENDPOINT,
        environment: str = "production",
        app_version: str = "1.0.0",
        max_breadcrumbs: int = 50,
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
        self._lock = threading.RLock()
        self._captured_events: Deque[Dict[str, Any]] = deque(maxlen=MAX_CAPTURED_EVENTS)
        self._hook_manager = GlobalHookManager(self._capture_raw)

        if install_hooks:
            self._hook_manager.install()

    @property
    def captured_events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._captured_events)

    def build_crash_payload(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Dict[str, Any]:
        exc_dto = normalize_exception(exc_type, exc_value, exc_tb)
        env_dto = collect_environment(
            app_version=self.app_version,
            environment_name=self.environment,
        )
        return {
            "project_key": self.project_key,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "platform": "python",
            "language": "python",
            "exception_type": exc_dto.error_type,
            "error_message": exc_dto.message,
            "stack_trace": exc_dto.format_stack_trace(),
            "environment": env_dto.to_dict(),
        }

    def capture_exception(
        self, exception: Optional[BaseException] = None
    ) -> Optional[Dict[str, Any]]:
        self._hook_manager.attach_asyncio_loop()
        if exception is not None:
            return self._capture_raw(type(exception), exception, exception.__traceback__)

        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_type is None and exc_value is None:
            return None
        return self._capture_raw(exc_type, exc_value, exc_tb)

    def _capture_raw(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Dict[str, Any]:
        self._hook_manager.attach_asyncio_loop()
        payload = self.build_crash_payload(exc_type, exc_value, exc_tb)
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

    def capture_exception(
        self, exception: Optional[BaseException] = None
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            active = self._client
        if active is None:
            return None
        return active.capture_exception(exception)

    def reset(self) -> None:
        self.bind_client(None)