import asyncio
from typing import Protocol

import httpx

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

    async def generate(self, prompt: str) -> DraftEnvelope:
        payload = {
            "model": self.settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": DraftEnvelope.model_json_schema(),
            "stream": False,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "num_ctx": self.settings.context,
                "num_predict": self.settings.max_output_tokens,
                "temperature": 0.1,
            },
        }
        try:
            async with self._gate:
                response = await self.client.post(
                    f"{self.settings.ollama_url}/api/chat", json=payload
                )
                response.raise_for_status()
            return DraftEnvelope.model_validate_json(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise BackendError("ollama_invalid_response") from exc


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
