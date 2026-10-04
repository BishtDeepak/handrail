"""Configuration: secrets stay secret, missing keys fail with an actionable message."""

from __future__ import annotations

import pytest

from handrail.config import ConfigError, Settings

pytestmark = pytest.mark.unit


def test_secrets_hidden_in_repr_and_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-000")
    settings = Settings(_env_file=None)
    assert "sk-test-000" not in repr(settings)
    assert "sk-test-000" not in settings.model_dump_json()
    assert settings.require_openai_key().get_secret_value() == "sk-test-000"


def test_empty_values_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    settings = Settings(_env_file=None)
    assert settings.openai_api_key is None
    assert settings.openai_base_url is None


def test_missing_key_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigError, match=r"OPENAI_API_KEY.*\.env"):
        Settings(_env_file=None).require_openai_key()


def test_judge_provider_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUDGE_PROVIDER", raising=False)
    assert Settings(_env_file=None).judge_provider == "none"
