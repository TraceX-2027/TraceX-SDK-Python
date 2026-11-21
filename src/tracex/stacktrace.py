from __future__ import annotations

from dataclasses import asdict, dataclass
import traceback
from types import TracebackType
from typing import Any, Dict, List, Optional, Type


@dataclass
class StackFrameDto:
    filename: str
    lineno: int
    function: str
    code_context: Optional[str] = None


@dataclass
class ExceptionDto:
    error_type: str
    message: str
    frames: List[StackFrameDto]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "frames": [asdict(frame) for frame in self.frames],
        }

    def format_stack_trace(self) -> str:
        lines: List[str] = ["Traceback (most recent call last):"]
        for frame in self.frames:
            lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.function}')
            if frame.code_context:
                lines.append(f"    {frame.code_context}")
        msg_part = f": {self.message}" if self.message else ""
        lines.append(f"{self.error_type}{msg_part}")
        return "\n".join(lines)


def _safe_str(value: Optional[BaseException]) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
        return "<unprintable exception>"


def normalize_exception(
    exc_type: Optional[Type[BaseException]],
    exc_value: Optional[BaseException],
    exc_tb: Optional[TracebackType],
) -> ExceptionDto:
    resolved_type = exc_type or (type(exc_value) if exc_value is not None else None)
    error_type = resolved_type.__name__ if resolved_type is not None else "UnknownError"
    message = _safe_str(exc_value) or error_type
    resolved_tb = exc_tb or getattr(exc_value, "__traceback__", None)

    frames: List[StackFrameDto] = []
    if resolved_tb is not None:
        for summary in traceback.extract_tb(resolved_tb):
            frames.append(
                StackFrameDto(
                    filename=summary.filename,
                    lineno=summary.lineno or 0,
                    function=summary.name,
                    code_context=summary.line.strip() if summary.line else None,
                )
            )

    return ExceptionDto(error_type=error_type, message=message, frames=frames)