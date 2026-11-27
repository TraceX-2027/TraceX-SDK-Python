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
        self._lock = threading.RLock()
        self._original_sys_hook: Any = None
        self._original_threading_hook: Any = None
        self._tracked_loops: List[Tuple[asyncio.AbstractEventLoop, Any, Any]] = []
        self._wrapped_policy: Optional[asyncio.AbstractEventLoopPolicy] = None
        self._original_new_event_loop: Any = None

    def install(self) -> None:
        with self._lock:
            if self._installed:
                return
            self._original_sys_hook = sys.excepthook
            sys.excepthook = self._sys_excepthook

            if hasattr(threading, "excepthook"):
                self._original_threading_hook = threading.excepthook
                threading.excepthook = self._threading_excepthook

            try:
                policy = asyncio.get_event_loop_policy()
                orig_new_loop = policy.new_event_loop
                manager = self

                def _wrapped_new_event_loop() -> asyncio.AbstractEventLoop:
                    loop = orig_new_loop()
                    manager.attach_asyncio_loop(loop)
                    return loop

                self._wrapped_policy = policy
                self._original_new_event_loop = orig_new_loop
                setattr(policy, "new_event_loop", _wrapped_new_event_loop)
            except Exception:
                pass

            self.attach_asyncio_loop()
            self._installed = True

    def uninstall(self) -> None:
        with self._lock:
            if not self._installed:
                return
            if self._original_sys_hook is not None and sys.excepthook == self._sys_excepthook:
                sys.excepthook = self._original_sys_hook
            self._original_sys_hook = None

            if (
                hasattr(threading, "excepthook")
                and self._original_threading_hook is not None
                and threading.excepthook == self._threading_excepthook
            ):
                threading.excepthook = self._original_threading_hook
            self._original_threading_hook = None

            if self._wrapped_policy is not None and self._original_new_event_loop is not None:
                try:
                    setattr(self._wrapped_policy, "new_event_loop", self._original_new_event_loop)
                except Exception:
                    pass
            self._wrapped_policy = None
            self._original_new_event_loop = None

            for loop, prev_handler, our_handler in self._tracked_loops:
                try:
                    if not loop.is_closed() and loop.get_exception_handler() == our_handler:
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

        with self._lock:
            self._tracked_loops = [
                (lp, prev, ours)
                for lp, prev, ours in self._tracked_loops
                if not lp.is_closed() and lp.get_exception_handler() == ours
            ]
            if any(tracked is target_loop for tracked, _, _ in self._tracked_loops):
                return

            previous_handler = target_loop.get_exception_handler()

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

            self._tracked_loops.append((target_loop, previous_handler, _asyncio_handler))
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