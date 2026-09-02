import pytest

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftKind


def test_settings_use_pinned_safe_defaults(monkeypatch):
    for name in ("QA_ROUTER_ENABLED", "QA_ROUTER_MODEL", "QA_ROUTER_CONTEXT"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.enabled is True
    assert settings.model == "qwen/qwen3.5-9b"
    assert settings.context == 16_384
    assert settings.ttl_seconds == 300
    assert settings.timeout_seconds == 90
    assert settings.max_input_chars == 40_000
    assert settings.max_parallel == 1
    assert settings.input_limit(DraftKind.SHORT_EXPLANATION) == 6_000
    assert settings.output_limit(DraftKind.SHORT_EXPLANATION) == 384
    assert settings.input_limit(DraftKind.LOG_SUMMARY) == 40_000
    assert settings.output_limit(DraftKind.TEST_CASES) == 2_048


def test_zero_disables_router(monkeypatch):
    monkeypatch.setenv("QA_ROUTER_ENABLED", "0")

    assert Settings.from_env().enabled is False


def test_disabled_marker_turns_off_router(monkeypatch, tmp_path):
    monkeypatch.setenv("QA_ROUTER_ENABLED", "1")
    monkeypatch.setenv("QA_ROUTER_DATA_DIR", str(tmp_path))
    (tmp_path / "disabled").touch()

    assert Settings.from_env().enabled is False


def test_non_loopback_or_unpinned_model_is_rejected():
    with pytest.raises(ValueError, match="pinned model"):
        Settings(model="another-model")
    with pytest.raises(ValueError, match="loopback"):
        Settings(lmstudio_url="https://remote.example.test")
