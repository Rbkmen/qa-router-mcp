from pathlib import Path

import httpx
import pytest

from qa_router_mcp.backends import HermesLearningBackend, OllamaDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.policy import PolicyError


@pytest.mark.asyncio
async def test_ollama_uses_direct_structured_request():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["model"] == "gemma4:12b-it-q4_K_M"
        assert body["options"]["num_ctx"] == 64_000
        assert body["stream"] is False
        assert body["format"]["title"] == "DraftEnvelope"
        return httpx.Response(
            200,
            json={"message": {"content": '{"draft":"A","unverified":["A"]}'}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await OllamaDraftBackend(Settings(), client).generate("prompt")

    assert result.draft == "A"
    await client.aclose()


@pytest.mark.asyncio
async def test_hermes_receives_only_validated_learning_text(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"stored", b""

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    settings = Settings(hermes_command=Path("/safe/qa-routine"), data_dir=tmp_path)

    result = await HermesLearningBackend(settings).apply("Use concise case titles")

    assert result == "stored"
    assert captured["args"][:5] == (
        "/safe/qa-routine",
        "--reasoning",
        "none",
        "--toolsets",
        "memory",
    )
    assert "Use concise case titles" in captured["args"][-1]
    assert set(captured["env"]) == {"HOME", "PATH", "HERMES_PROFILE"}


@pytest.mark.asyncio
async def test_hermes_rejects_corporate_artifact_before_subprocess(tmp_path):
    settings = Settings(hermes_command=Path("/safe/qa-routine"), data_dir=tmp_path)

    with pytest.raises(PolicyError, match="learning_content_forbidden"):
        await HermesLearningBackend(settings).apply("Remember ABC-123")


@pytest.mark.asyncio
async def test_invalid_schema_is_repaired_once():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else '{"draft":"A","unverified":["A"]}'
        return httpx.Response(200, json={"message": {"content": content}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await OllamaDraftBackend(Settings(), client).generate("prompt")

    assert result.draft == "A"
    assert calls == 2
    await client.aclose()
