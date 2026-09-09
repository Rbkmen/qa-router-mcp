import asyncio
from functools import lru_cache
from time import monotonic
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import lmstudio as lms
from pydantic import ValidationError

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, GenerationStats, TokenCount
from qa_router_mcp.prompts import SYSTEM_PROMPT


@lru_cache(maxsize=2)
def _lmstudio_client(api_host: str) -> lms.Client:
    return lms.Client(api_host)


class BackendError(RuntimeError):
    def __init__(self, code: str, stats: GenerationStats | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.stats = stats or GenerationStats()


class DraftBackend(Protocol):
    async def count_tokens(self, prompt: str) -> int | TokenCount: ...

    async def generate(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        allow_schema_repair: bool = True,
    ) -> DraftEnvelope: ...


class LMStudioDraftBackend:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=settings.timeout_seconds,
            trust_env=False,
        )
        self._gate = asyncio.Semaphore(settings.max_parallel)

    def _count_messages_sync(self, messages: list[dict[str, str]]) -> TokenCount:
        api_host = urlsplit(self.settings.lmstudio_url).netloc
        client = _lmstudio_client(api_host)
        cold_start = not any(
            getattr(model, "identifier", None) == self.settings.model
            for model in client.llm.list_loaded()
        )
        load_started = monotonic()
        model = client.llm.model(
            self.settings.model,
            ttl=self.settings.ttl_seconds,
            config={"contextLength": self.settings.context},
        )
        if model.get_context_length() < self.settings.context:
            raise BackendError("local_model_context_mismatch")
        model_load_ms = (monotonic() - load_started) * 1_000 if cold_start else 0.0
        tokenization_started = monotonic()
        chat = lms.Chat.from_history({"messages": messages})
        formatted_prompt = model.apply_prompt_template(chat)
        tokens = len(model.tokenize(formatted_prompt))
        return TokenCount(
            tokens=tokens,
            model_load_ms=model_load_ms,
            tokenization_ms=(monotonic() - tokenization_started) * 1_000,
            cold_start=cold_start,
        )

    def _count_tokens_sync(self, prompt: str) -> TokenCount:
        return self._count_messages_sync(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )

    async def count_tokens(self, prompt: str) -> TokenCount:
        try:
            async with self._gate:
                return await asyncio.to_thread(self._count_tokens_sync, prompt)
        except BackendError:
            raise
        except Exception as exc:
            raise BackendError("local_tokenizer_error") from exc

    async def _request(self, payload: dict[str, object]) -> tuple[str, GenerationStats]:
        try:
            response = await self.client.post(
                f"{self.settings.lmstudio_url}/v1/chat/completions",
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            message = body["choices"][0]["message"]
            if not isinstance(message, dict):
                raise TypeError("LM Studio message must be an object")
            content = message.get("content") or message.get("reasoning_content")
            if not isinstance(content, str):
                raise TypeError("LM Studio message content must be text")
            usage = body.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            choice = body["choices"][0]
            stats = GenerationStats(
                prompt_tokens=_non_negative_int(usage.get("prompt_tokens")),
                output_tokens=_non_negative_int(usage.get("completion_tokens")),
                requests=1,
                truncated=choice.get("finish_reason") in {"length", "max_tokens"},
                usage_available=(
                    _is_non_negative_int(usage.get("prompt_tokens"))
                    and _is_non_negative_int(usage.get("completion_tokens"))
                ),
            )
            return content, stats
        except httpx.HTTPStatusError as exc:
            raise BackendError(
                "local_model_invalid_response",
                GenerationStats(requests=1),
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(
                "local_model_transport_error",
                GenerationStats(requests=1),
            ) from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise BackendError(
                "local_model_invalid_response",
                GenerationStats(requests=1),
            ) from exc

    async def _request_with_transport_retry(
        self,
        payload: dict[str, object],
    ) -> tuple[str, GenerationStats]:
        failed_stats = GenerationStats()
        for attempt in range(2):
            try:
                content, stats = await self._request(payload)
                return content, failed_stats.merged(stats)
            except BackendError as exc:
                failed_stats = failed_stats.merged(exc.stats)
                if exc.code != "local_model_transport_error" or attempt == 1:
                    raise BackendError(exc.code, failed_stats) from exc
        raise BackendError("local_model_transport_error", failed_stats)

    async def generate(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        allow_schema_repair: bool = True,
    ) -> DraftEnvelope:
        async with self._gate:
            return await self._generate_unlocked(
                prompt,
                max_output_tokens=max_output_tokens,
                allow_schema_repair=allow_schema_repair,
            )

    async def _generate_unlocked(
        self,
        prompt: str,
        *,
        max_output_tokens: int | None = None,
        allow_schema_repair: bool = True,
    ) -> DraftEnvelope:
        response_schema = _response_schema()
        payload: dict[str, object] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "draft_envelope",
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "stream": False,
            "ttl": self.settings.ttl_seconds,
            "max_tokens": (
                self.settings.max_output_tokens if max_output_tokens is None else max_output_tokens
            ),
            "temperature": 0,
        }
        stats = GenerationStats()
        attempts = 2 if allow_schema_repair else 1
        for attempt in range(attempts):
            content, request_stats = await self._request_with_transport_retry(payload)
            stats = stats.merged(request_stats)
            try:
                result = DraftEnvelope.model_validate_json(content)
                result.set_generation_stats(stats)
                return result
            except ValidationError as exc:
                if attempt == attempts - 1:
                    raise BackendError("local_model_invalid_schema", stats) from exc
                messages = payload["messages"]
                assert isinstance(messages, list)
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Return valid JSON only. Keep every unsupported statement "
                            "in unverified."
                        ),
                    }
                )
                try:
                    repair_tokens = await asyncio.to_thread(self._count_messages_sync, messages)
                except Exception as tokenizer_error:
                    raise BackendError("local_tokenizer_error", stats) from tokenizer_error
                output_limit = int(payload["max_tokens"])
                if (
                    repair_tokens.tokens + output_limit + self.settings.context_reserve_tokens
                    > self.settings.context
                ):
                    raise BackendError("local_model_token_budget_exceeded", stats)
        raise BackendError("local_model_invalid_schema", stats)


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _response_schema() -> dict[str, object]:
    string_list = {"type": "array", "items": {"type": "string"}}
    return {
        "title": "DraftEnvelope",
        "type": "object",
        "properties": {
            "draft": {"type": "string"},
            "assumptions": string_list,
            "unverified": string_list,
        },
        "required": ["draft", "assumptions", "unverified"],
        "additionalProperties": False,
    }
