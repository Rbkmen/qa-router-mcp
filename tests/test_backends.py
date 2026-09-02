import httpx
import pytest

from qa_router_mcp.backends import LMStudioDraftBackend
from qa_router_mcp.config import Settings


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
                        "message": {
                            "content": '{"draft":"A","unverified":["A"]}'
                        },
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
    assert result.generation_stats.truncated is False
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
                            "reasoning_content": (
                                '{"draft":"A","unverified":["A"]}'
                            ),
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
async def test_invalid_schema_is_repaired_once():
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

    result = await LMStudioDraftBackend(Settings(), client).generate("prompt")

    assert result.draft == "A"
    assert calls == 2
    assert result.generation_stats.requests == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_length_stop_is_exposed_as_truncation():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"draft":"A","unverified":["A"]}'
                        },
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
            json={
                "choices": [
                    {"message": {"content": '{"draft":"A","unverified":["A"]}'}}
                ]
            },
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
async def test_explicit_zero_output_limit_is_not_replaced_by_default():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["max_tokens"] == 0
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"draft":"A","unverified":["A"]}'}}
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    result = await LMStudioDraftBackend(Settings(), client).generate(
        "prompt",
        max_output_tokens=0,
    )

    assert result.status == "ok"
    await client.aclose()
