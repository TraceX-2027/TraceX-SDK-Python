from __future__ import annotations

import threading

import tracex
from tracex.breadcrumbs import BreadcrumbBuffer
from tracex.client import Hub


def test_ring_buffer_fifo_eviction_at_50() -> None:
    buf = BreadcrumbBuffer(maxlen=50)
    for idx in range(75):
        buf.add(message=f"step_{idx}", category="system")

    snap = buf.snapshot()
    assert len(snap) == 50
    assert snap[0]["message"] == "step_25"
    assert snap[-1]["message"] == "step_74"


def test_breadcrumb_categories_and_thread_safety() -> None:
    Hub.current().reset()
    client = tracex.init(project_key="proj_crumbs", install_hooks=False)

    def worker(tid: int) -> None:
        for i in range(10):
            tracex.add_breadcrumb(
                message=f"query_{tid}_{i}",
                category="db.query",
                data={"row": i},
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(client.breadcrumbs) == 50
    payload = tracex.capture_exception(RuntimeError("db timeout"))
    assert payload is not None
    assert len(payload["breadcrumbs"]) == 50
    assert all(b["category"] == "db.query" for b in payload["breadcrumbs"])
    Hub.current().reset()