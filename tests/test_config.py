import pytest

from qa_router_mcp.config import Settings


def test_settings_use_pinned_safe_defaults(monkeypatch):
    for name in ("QA_ROUTER_ENABLED", "QA_ROUTER_MODEL", "QA_ROUTER_CONTEXT"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.enabled is True
    assert settings.model == "gemma4:12b-it-q4_K_M"
    assert settings.context == 64_000
    assert settings.max_input_chars == 40_000
    assert settings.max_parallel == 1


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
        Settings(ollama_url="https://remote.example.test")
