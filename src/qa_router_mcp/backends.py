import asyncio
from typing import Protocol

import httpx
from pydantic import ValidationError

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope
from qa_router_mcp.policy import validate_learning_text


class BackendError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DraftBackend(Protocol):
    async def generate(self, prompt: str) -> DraftEnvelope: ...


class LearningBackend(Protocol):
    async def apply(self, text: str) -> str: ...


class OllamaDraftBackend:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._gate = asyncio.Semaphore(1)

    async def _request(self, payload: dict[str, object]) -> str:
        try:
            async with self._gate:
                response = await self.client.post(
                    f"{self.settings.ollama_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
            return response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            raise BackendError("ollama_invalid_response") from exc

    async def generate(self, prompt: str) -> DraftEnvelope:
        payload: dict[str, object] = {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": DraftEnvelope.model_json_schema(),
            "think": False,
            "stream": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "num_ctx": self.settings.context,
                "num_predict": self.settings.max_output_tokens,
                "temperature": 0.1,
            },
        }
        for attempt in range(2):
            content = await self._request(payload)
            try:
                return DraftEnvelope.model_validate_json(content)
            except ValidationError as exc:
                if attempt == 1:
                    raise BackendError("ollama_invalid_schema") from exc
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
        raise BackendError("ollama_invalid_schema")


class HermesLearningBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def apply(self, text: str) -> str:
        safe_text = validate_learning_text(text)
        prompt = (
            "Store this user-approved generic QA preference using the memory tool. "
            "Do not create or edit skills, infer project facts, or rewrite the text:\n"
            + safe_text
        )
        env = {
            "HOME": "/Users/andreiviarshko",
            "PATH": "/Users/andreiviarshko/.local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "HERMES_PROFILE": "qa-routine",
        }
        process = await asyncio.create_subprocess_exec(
            str(self.settings.hermes_command),
            "--reasoning",
            "none",
            "--toolsets",
            "memory",
            "--ignore-rules",
            "--oneshot",
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.timeout_seconds
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise BackendError("hermes_timeout") from exc
        if process.returncode != 0:
            raise BackendError("hermes_failed")
        return stdout.decode().strip()
