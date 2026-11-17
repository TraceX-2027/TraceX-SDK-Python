from __future__ import annotations

import asyncio
import sys
import threading

import pytest

import tracex
from tracex.client import Hub


@pytest.fixture(autouse=True)
def reset_hub() -> None:
    Hub.current().reset()


def test_sys_excepthook_traps_crash_and_ignores_keyboard_interrupt() -> None:
    original_hook = sys.excepthook
    prior_called = []

    def fake_prior(exc_type, exc_value, exc_tb) -> None:  # type: ignore[no-untyped-def]
        prior_called.append(exc_type)

    sys.excepthook = fake_prior
    try:
        client = tracex.init(project_key="proj_hooks_1", install_hooks=True)
        try:
            raise RuntimeError("unhandled main thread crash")
        except RuntimeError as err:
            sys.excepthook(type(err), err, err.__traceback__)

        assert len(client.captured_events) == 1
        assert client.captured_events[0]["exception_type"] == "RuntimeError"
        assert prior_called == [RuntimeError]

        kb_err = KeyboardInterrupt()
        sys.excepthook(KeyboardInterrupt, kb_err, None)
        assert len(client.captured_events) == 1
    finally:
        Hub.current().reset()
        sys.excepthook = original_hook


def test_threading_excepthook_traps_thread_crash_and_ignores_system_exit() -> None:
    original_thread_hook = threading.excepthook
    try:
        client = tracex.init(project_key="proj_hooks_2", install_hooks=True)

        def worker_crash() -> None:
            raise ZeroDivisionError("background thread crash")

        def worker_exit() -> None:
            raise SystemExit(0)

        t1 = threading.Thread(target=worker_crash)
        t1.start()
        t1.join()

        t2 = threading.Thread(target=worker_exit)
        t2.start()
        t2.join()

        assert len(client.captured_events) == 1
        assert client.captured_events[0]["exception_type"] == "ZeroDivisionError"
    finally:
        Hub.current().reset()
        threading.excepthook = original_thread_hook


def test_asyncio_unhandled_task_exception_and_cleanup() -> None:
    client = tracex.init(project_key="proj_hooks_3", install_hooks=True)

    async def runner() -> None:
        client._hook_manager.attach_asyncio_loop()

        async def crashing_task() -> None:
            raise KeyError("missing_async_key")

        task = asyncio.create_task(crashing_task())
        with pytest.raises(KeyError):
            await task

        # Trigger genuine unhandled background task exception
        bg_task = asyncio.create_task(crashing_task())
        await asyncio.sleep(0.05)
        del bg_task

    try:
        asyncio.run(runner())
        assert any(e["exception_type"] == "KeyError" for e in client.captured_events)
    finally:
        Hub.current().reset()