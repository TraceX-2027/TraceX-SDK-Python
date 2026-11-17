from __future__ import annotations

import asyncio
import sys
import threading
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

ExceptionCallback = Callable[
    [Optional[Type[BaseException]], Optional[BaseException], Optional[TracebackType]],
    Any,
]

_IGNORED_EXCEPTIONS: Tuple[Type[BaseException], ...] = (KeyboardInterrupt, SystemExit)


class GlobalHookManager:
    def __init__(self, on_exception: ExceptionCallback) -> None:
        self._on_exception = on_exception
        self._installed = False
        self._original_sys_hook: Any = None
        self._original_threading_hook: Any = None
        self._tracked_loops: List[Tuple[asyncio.AbstractEventLoop, Any]] = []

    def install(self) -> None:
        if self._installed:
            return
        self._original_sys_hook = sys.excepthook
        sys.excepthook = self._sys_excepthook

        if hasattr(threading, "excepthook"):
            self._original_threading_hook = threading.excepthook
            threading.excepthook = self._threading_excepthook

        self.attach_asyncio_loop()
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        if self._original_sys_hook is not None:
            sys.excepthook = self._original_sys_hook
            self._original_sys_hook = None

        if hasattr(threading, "excepthook") and self._original_threading_hook is not None:
            threading.excepthook = self._original_threading_hook
            self._original_threading_hook = None

        for loop, prev_handler in self._tracked_loops:
            try:
                if not loop.is_closed():
                    loop.set_exception_handler(prev_handler)
            except Exception:
                pass
        self._tracked_loops.clear()
        self._installed = False

    def attach_asyncio_loop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        target_loop = loop
        if target_loop is None:
            try:
                target_loop = asyncio.get_running_loop()
            except RuntimeError:
                return

        if any(tracked is target_loop for tracked, _ in self._tracked_loops):
            return

        previous_handler = target_loop.get_exception_handler()
        self._tracked_loops.append((target_loop, previous_handler))

        def _asyncio_handler(
            active_loop: asyncio.AbstractEventLoop, context: Dict[str, Any]
        ) -> None:
            exc = context.get("exception")
            if isinstance(exc, BaseException) and not isinstance(exc, _IGNORED_EXCEPTIONS):
                try:
                    self._on_exception(type(exc), exc, exc.__traceback__)
                except Exception:
                    pass
            if previous_handler is not None:
                previous_handler(active_loop, context)
            else:
                active_loop.default_exception_handler(context)

        target_loop.set_exception_handler(_asyncio_handler)

    def _sys_excepthook(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: Optional[TracebackType],
    ) -> None:
        if not issubclass(exc_type, _IGNORED_EXCEPTIONS):
            try:
                self._on_exception(exc_type, exc_value, exc_tb)
            except Exception:
                pass
        if self._original_sys_hook is not None:
            self._original_sys_hook(exc_type, exc_value, exc_tb)

    def _threading_excepthook(self, args: Any) -> None:
        exc_type = getattr(args, "exc_type", None)
        exc_value = getattr(args, "exc_value", None)
        exc_tb = getattr(args, "exc_traceback", None)
        if exc_type is not None and not issubclass(exc_type, _IGNORED_EXCEPTIONS):
            try:
                self._on_exception(exc_type, exc_value, exc_tb)
            except Exception:
                pass
        if self._original_threading_hook is not None:
            self._original_threading_hook(args)