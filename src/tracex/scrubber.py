from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Pattern, Set, Tuple

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS: Set[str] = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "secret_key",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "auth_token",
    "authorization",
    "bearer",
    "token",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
}

_REGEX_RULES: List[Tuple[Pattern[str], str]] = [
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]+=*"),
        f"Bearer {REDACTED}",
    ),
    (
        re.compile(
            r'(?i)\b(password|passwd|pwd|secret|secret_key|api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token)\b(\s*[:=]\s*)(["\']?)([^\s"\',;&}]+)\3'
        ),
        rf"\1\2\3{REDACTED}\3",
    ),
    (
        re.compile(r"\b(?:sk|pk|rk|api|key)[_-](?:live|test|prod)?[_-]?[A-Za-z0-9]{12,}\b"),
        REDACTED,
    ),
    (
        re.compile(r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4}(?!\d)"),
        REDACTED,
    ),
]


class PIIScrubber:
    def __init__(self, extra_sensitive_keys: Optional[Set[str]] = None) -> None:
        self._sensitive_keys: Set[str] = set(_SENSITIVE_KEYS)
        if extra_sensitive_keys:
            self._sensitive_keys.update(k.lower() for k in extra_sensitive_keys)

    def scrub_text(self, text: str) -> str:
        if not text:
            return text
        result = text
        for pattern, replacement in _REGEX_RULES:
            result = pattern.sub(replacement, result)
        return result

    def scrub_value(self, value: Any, key_hint: str = "") -> Any:
        if key_hint and key_hint.lower().strip() in self._sensitive_keys:
            if isinstance(value, str) and value.lower().startswith("bearer "):
                return f"Bearer {REDACTED}"
            return REDACTED

        if isinstance(value, str):
            return self.scrub_text(value)
        if isinstance(value, dict):
            return self.scrub_dict(value)
        if isinstance(value, list):
            return [self.scrub_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.scrub_value(item) for item in value)
        return value

    def scrub_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            cleaned[key_str] = self.scrub_value(v, key_hint=key_str)
        return cleaned