import asyncio
import time
from threading import Lock

import httpx
import pytest

import qa_router_mcp.backends as backends_module
from qa_router_mcp.backends import BackendError, LMStudioDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import TokenCount


@pytest.mark.asyncio
async def test_lmstudio_counts_formatted_prompt_tokens(monkeypatch):
    calls = {}

    class FakeChat:
        @classmethod
        def from_history(cls, history):
            calls["history"] = history
            return "chat"

    class FakeModel:
        def get_context_length(self):
            return 16_384

        def apply_prompt_template(self, chat):
            calls["chat"] = chat
            return "formatted prompt"

        def tokenize(self, text):
            calls["text"] = text
            return list(range(321))

    monkeypatch.setattr(backends_module.lms, "Chat", FakeChat)

    class FakeLlmNamespace:
        def list_loaded(self):
            return []

        def model(self, model, *, ttl, config):
            calls.update(model=model, ttl=ttl, config=config)
            return FakeModel()

    class FakeClient:
        llm = FakeLlmNamespace()

    monkeypatch.setattr(
        backends_module,
        "_lmstudio_client",
        lambda api_host: calls.update(api_host=api_host) or FakeClient(),
    )

    backend = LMStudioDraftBackend(Settings())
    token_count = await backend.count_tokens("source prompt")

    assert token_count.tokens == 321
    assert token_count.cold_start is True
    assert token_count.model_load_ms >= 0
    assert token_count.tokenization_ms >= 0
    assert calls == {
        "model": "qwen/qwen3.5-9b",
        "ttl": 300,
        "config": {"contextLength": 16_384},
        "api_host": "127.0.0.1:1234",
        "history": {
            "messages": [
                {"role": "system", "content": backends_module.SYSTEM_PROMPT},
                {"role": "user", "content": "source prompt"},
            ]
        },
        "chat": "chat",
        "text": "formatted prompt",
    }
    await backend.client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_rejects_model_with_unverified_context_length(monkeypatch):
    class FakeModel:
        def get_context_length(self):
            return 8_192

        def apply_prompt_template(self, chat):
            return "formatted prompt"

        def tokenize(self, text):
            return [1]

    class FakeLlmNamespace:
        def list_loaded(self):
            return []

        def model(self, model, *, ttl, config):
            assert config == {"contextLength": 16_384}
            return FakeModel()

    class FakeClient:
        llm = FakeLlmNamespace()

    monkeypatch.setattr(backends_module, "_lmstudio_client", lambda _: FakeClient())

    backend = LMStudioDraftBackend(Settings())
    with pytest.raises(BackendError, match="local_model_context_mismatch"):
        await backend.count_tokens("prompt")
    await backend.client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_accepts_model_with_larger_context_length(monkeypatch):
    class FakeModel:
        def get_context_length(self):
            return 92_672

        def apply_prompt_template(self, chat):
            return "formatted prompt"

        def tokenize(self, text):
            return [1, 2]

    class FakeLlmNamespace:
        def list_loaded(self):
            return []

        def model(self, model, *, ttl, config):
            assert config == {"contextLength": 16_384}
            return FakeModel()

    class FakeClient:
        llm = FakeLlmNamespace()

    monkeypatch.setattr(backends_module, "_lmstudio_client", lambda _: FakeClient())

    backend = LMStudioDraftBackend(Settings())
    token_count = await backend.count_tokens("prompt")

    assert token_count.tokens == 2
    await backend.client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_uses_direct_structured_request():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["model"] == "qwen/qwen3.5-9b"
        assert body["max_tokens"] == 512
        assert body["temperature"] == 0
        assert body["stream"] is False
        assert body["ttl"] == 300
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1] == {"role": "user", "content": "prompt"}
        response_format = body["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        schema = response_format["json_schema"]["schema"]
        assert schema["title"] == "DraftEnvelope"
        assert {"draft", "unverified"} <= set(schema.get("required", []))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"draft":"A","unverified":["A"]}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 21, "completion_tokens": 9},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate(
        "prompt",
        max_output_tokens=512,
    )

    assert result.draft == "A"
    assert result.generation_stats.prompt_tokens == 21
    assert result.generation_stats.output_tokens == 9
    assert result.generation_stats.requests == 1
    assert result.generation_stats.usage_available is True
    assert result.generation_stats.truncated is False
    await client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_marks_usage_unavailable_when_response_omits_usage():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"draft":"A","unverified":[]}'},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate(
        "prompt",
        max_output_tokens=512,
    )

    assert result.generation_stats.usage_available is False
    await client.aclose()


@pytest.mark.asyncio
async def test_tokenization_and_generation_share_one_concurrency_gate(monkeypatch):
    state = {"active": 0, "maximum": 0}
    lock = Lock()

    def enter():
        with lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])

    def leave():
        with lock:
            state["active"] -= 1

    def count_tokens(_):
        enter()
        time.sleep(0.03)
        leave()
        return TokenCount(tokens=10, model_load_ms=0, tokenization_ms=0, cold_start=False)

    async def handler(request: httpx.Request) -> httpx.Response:
        enter()
        await asyncio.sleep(0.03)
        leave()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"draft":"A","unverified":[]}'}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = LMStudioDraftBackend(Settings(), client)
    monkeypatch.setattr(backend, "_count_tokens_sync", count_tokens)

    await asyncio.gather(backend.count_tokens("prompt"), backend.generate("prompt"))

    assert state["maximum"] == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_lmstudio_accepts_structured_json_from_reasoning_channel():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning_content": ('{"draft":"A","unverified":["A"]}'),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert result.draft == "A"
    assert result.generation_stats.output_tokens == 8
    await client.aclose()


@pytest.mark.asyncio
async def test_invalid_schema_is_repaired_once(monkeypatch):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = "not-json" if calls == 1 else '{"draft":"A","unverified":["A"]}'
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    backend = LMStudioDraftBackend(Settings(), client)
    monkeypatch.setattr(
        backend,
        "_count_messages_sync",
        lambda _: TokenCount(tokens=100, model_load_ms=0, tokenization_ms=0, cold_start=False),
    )
    result = await backend.generate("prompt")

    assert result.draft == "A"
    assert calls == 2
    assert result.generation_stats.requests == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_schema_repair_rechecks_context_budget(monkeypatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    backend = LMStudioDraftBackend(Settings(), client)
    monkeypatch.setattr(
        backend,
        "_count_messages_sync",
        lambda _: TokenCount(tokens=16_000, model_load_ms=0, tokenization_ms=0, cold_start=False),
    )

    from qa_router_mcp.backends import BackendError

    with pytest.raises(BackendError, match="local_model_token_budget_exceeded"):
        await backend.generate("prompt")

    await client.aclose()


@pytest.mark.asyncio
async def test_length_stop_is_exposed_as_truncation():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"draft":"A","unverified":["A"]}'},
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert result.generation_stats.truncated is True
    await client.aclose()


@pytest.mark.asyncio
async def test_transport_error_is_retried_once():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"draft":"A","unverified":["A"]}'}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert result.draft == "A"
    assert result.generation_stats.requests == 2
    assert calls == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_invalid_response_is_not_retried():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    from qa_router_mcp.backends import BackendError

    with pytest.raises(BackendError, match="local_model_invalid_response"):
        await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_http_status_error_is_not_retried():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad request"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    from qa_router_mcp.backends import BackendError

    with pytest.raises(BackendError, match="local_model_invalid_response"):
        await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert calls == 1
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"choices": []}, {"choices": [{"message": []}]}])
async def test_malformed_choices_return_service_fallback(tmp_path, body):
    from qa_router_mcp.contracts import DraftKind
    from qa_router_mcp.service import RouterService

    class Backend(LMStudioDraftBackend):
        async def count_tokens(self, prompt):
            return 100

    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        settings = Settings(data_dir=tmp_path)
        result = await RouterService(settings, Backend(settings, client)).draft(
            DraftKind.REWRITE, "Synthetic text"
        )
    assert result.status == "fallback"
    assert result.reason == "local_model_invalid_response"
    assert calls == 1


@pytest.mark.asyncio
async def test_explicit_zero_output_limit_is_not_replaced_by_default():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["max_tokens"] == 0
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"draft":"A","unverified":["A"]}'}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate(
        "prompt",
        max_output_tokens=0,
    )

    assert result.status == "ok"
    await client.aclose()


@pytest.mark.asyncio
async def test_schema_repair_tokenizer_failure_preserves_request_stats(monkeypatch):
    from qa_router_mcp.backends import BackendError

    def fail(_):
        raise RuntimeError("tokenizer unavailable")

    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = LMStudioDraftBackend(Settings(), client)
        monkeypatch.setattr(backend, "_count_messages_sync", fail)
        with pytest.raises(BackendError, match="local_tokenizer_error") as error:
            await backend.generate("prompt")
        assert error.value.stats.requests == 1
