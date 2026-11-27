from __future__ import annotations

import tracex
from tracex.client import Hub
from tracex.scrubber import PIIScrubber, REDACTED


def test_scrubber_masks_bearer_passwords_apikeys_and_cards() -> None:
    scrubber = PIIScrubber()
    raw_text = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig "
        "password=SuperSecret123! "
        "api_key=sk_live_9876543210abcdef "
        "card=4532-0151-1283-0366"
    )
    cleaned = scrubber.scrub_text(raw_text)
    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert f"Bearer {REDACTED}" in cleaned
    assert "SuperSecret123!" not in cleaned
    assert "sk_live_9876543210abcdef" not in cleaned
    assert "4532-0151-1283-0366" not in cleaned
    assert cleaned.count(REDACTED) == 4


def test_capture_payload_redacts_breadcrumbs_and_error_message() -> None:
    Hub.current().reset()
    tracex.init(project_key="proj_pii", install_hooks=False)
    tracex.add_breadcrumb(
        message="GET /login password=MySecretPass",
        category="network.http",
        data={"authorization": "Bearer secret_token_xyz", "card_number": "4111222233334444"},
    )
    payload = tracex.capture_exception(ValueError("Failed with api_key=sk_test_1234567890abcd"))
    assert payload is not None
    assert "sk_test_1234567890abcd" not in payload["error_message"]
    assert REDACTED in payload["error_message"]

    crumb = payload["breadcrumbs"][0]
    assert "MySecretPass" not in crumb["message"]
    assert crumb["data"]["authorization"] == f"Bearer {REDACTED}"
    assert crumb["data"]["card_number"] == REDACTED
    Hub.current().reset()