from __future__ import annotations

import pytest

import tracex
from tracex.client import DEFAULT_ENDPOINT, Hub


@pytest.fixture(autouse=True)
def reset_hub() -> None:
    Hub.current().reset()


def test_init_signature_and_defaults() -> None:
    client = tracex.init(project_key="proj_test_123", install_hooks=False)
    assert client.project_key == "proj_test_123"
    assert client.endpoint == DEFAULT_ENDPOINT
    assert client.environment == "production"
    assert client.app_version == "1.0.0"
    assert client.max_breadcrumbs == 50


def test_init_rejects_blank_project_key() -> None:
    with pytest.raises(ValueError):
        tracex.init(project_key="   ", install_hooks=False)


def test_capture_before_init_returns_none() -> None:
    assert tracex.capture_exception(RuntimeError("early")) is None


def test_capture_explicit_and_no_arg_exception_payload() -> None:
    tracex.init(
        project_key="proj_test_123",
        endpoint="https://custom.tracex.io/api/v1/crashes",
        environment="staging",
        app_version="2.1.0",
        max_breadcrumbs=25,
        install_hooks=False,
    )

    try:
        raise ValueError("invalid payload schema")
    except ValueError as err:
        explicit_payload = tracex.capture_exception(err)
        no_arg_payload = tracex.capture_exception()

    assert explicit_payload is not None
    assert no_arg_payload is not None

    for payload in (explicit_payload, no_arg_payload):
        assert payload["project_key"] == "proj_test_123"
        assert "occurred_at" in payload
        assert payload["platform"] == "python"
        assert payload["language"] == "python"
        assert payload["exception_type"] == "ValueError"
        assert payload["error_message"] == "invalid payload schema"
        assert "Traceback (most recent call last):" in payload["stack_trace"]
        assert "ValueError: invalid payload schema" in payload["stack_trace"]
        assert "device_environment" not in payload

        env = payload["environment"]
        assert isinstance(env, dict)
        assert env["app_version"] == "2.1.0"
        assert env["environment_name"] == "staging"
        assert isinstance(env["hostname"], str) and len(env["hostname"]) > 0
        assert isinstance(env["process_ram_mb"], float)
        assert env["process_ram_mb"] > 0.0