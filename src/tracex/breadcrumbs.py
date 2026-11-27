from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any, Deque, Dict, List, Optional, Set

ALLOWED_CATEGORIES: Set[str] = {"network.http", "db.query", "system", "custom"}
DEFAULT_MAX_BREADCRUMBS = 50


@dataclass
class Breadcrumb:
    category: str
    message: str
    level: str = "info"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BreadcrumbBuffer:
    def __init__(self, maxlen: int = DEFAULT_MAX_BREADCRUMBS) -> None:
        if maxlen < 0:
            raise ValueError("maxlen must be non-negative")
        self._maxlen = maxlen
        self._lock = threading.RLock()
        self._buffer: Deque[Breadcrumb] = deque(maxlen=maxlen)

    @property
    def maxlen(self) -> int:
        return self._maxlen

    def add(
        self,
        message: str,
        category: str = "custom",
        level: str = "info",
        data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> Breadcrumb:
        normalized_category = category if category in ALLOWED_CATEGORIES else "custom"
        crumb_data = dict(data) if data else {}
        if category not in ALLOWED_CATEGORIES and category:
            crumb_data.setdefault("original_category", category)

        crumb = Breadcrumb(
            category=normalized_category,
            message=message,
            level=level or "info",
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            data=crumb_data,
        )
        with self._lock:
            self._buffer.append(crumb)
        return crumb

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [crumb.to_dict() for crumb in self._buffer]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)