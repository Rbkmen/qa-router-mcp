# QA Router MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one local STDIO MCP server that lets Codex delegate safe QA drafting directly to Gemma and send only explicitly approved sanitized learning proposals to Hermes.

**Architecture:** Codex calls six narrow FastMCP tools. Draft tools sanitize their inputs and use Ollama directly without an application-level session; learning tools keep a local approval queue and invoke the isolated Hermes profile only after explicit approval. Policy failures and backend failures return typed fallback envelopes so Codex always remains the final authority.

**Tech Stack:** Python 3.12+, uv, FastMCP 3.x, Pydantic 2.x, HTTPX, pytest, pytest-asyncio, Ruff, Ollama 0.33.0, Hermes Agent 0.20.6, Gemma `gemma4:12b-it-q4_K_M`.

**Spec:** `docs/superpowers/specs/2026-08-30-qa-router-mcp-design.md`

## Global Constraints

- Python must be `>=3.12`; runtime and development commands use `uv`.
- FastMCP must remain `>=3.3,<4.0`; Pydantic must remain `>=2.11,<3.0`.
- The only model is `gemma4:12b-it-q4_K_M`; context is `64000`; local concurrency is one.
- Transient drafts call Ollama directly; Hermes must never receive transient task, Jira, code, repository, log, incident, account, or infrastructure content.
- Hermes receives only an explicitly approved proposal after deterministic sanitization and policy validation.
- Hermes learning calls expose only the `memory` toolset; version one never creates or rewrites Hermes skills.
- No tool may read corporate MCP configuration, modify a repository, execute arbitrary shell, browse, publish, merge, transition, delete, or approve external state.
- Router logs may contain tool name, duration, outcome, and error category, but never prompts, drafts, proposal text, or rejected content.
- Every draft is marked unverified; Codex owns evidence collection, final coverage, severity, release readiness, code edits, and external writes.
- One invalid model response may be repaired once; there are no unbounded retries.
- The feature switch `QA_ROUTER_ENABLED=0` disables local delegation without affecting any other Codex tool.

## File Map

```text
pyproject.toml                              package metadata, dependencies, scripts, lint/test config
src/qa_router_mcp/__init__.py              package version
src/qa_router_mcp/__main__.py              `python -m qa_router_mcp` entry point
src/qa_router_mcp/config.py                validated environment-based settings
src/qa_router_mcp/contracts.py             public input/output and learning models
src/qa_router_mcp/policy.py                classification, secret rejection, deterministic sanitization
src/qa_router_mcp/prompts.py               bounded prompts for the three draft categories
src/qa_router_mcp/backends.py              backend protocols, direct Ollama client, Hermes subprocess adapter
src/qa_router_mcp/store.py                 pending/approved proposal persistence
src/qa_router_mcp/events.py                content-free JSON operational events on stderr
src/qa_router_mcp/service.py               policy → prompt → backend → validation orchestration
src/qa_router_mcp/server.py                six FastMCP tool registrations and stdio startup
scripts/qa-router-mcp                      clean-environment launcher used by Codex
codex/skills/qa-local-routing/SKILL.md      automatic Codex routing rules
tests/test_config.py                       settings validation
tests/test_contracts.py                    schema and invariant tests
tests/test_policy.py                       secret, identifier, size, and forbidden-decision tests
tests/test_backends.py                     Ollama and Hermes adapter tests without real inference
tests/test_store.py                        proposal lifecycle and safe persistence tests
tests/test_service.py                      end-to-end service behavior with fake backends
tests/test_server.py                       FastMCP registration and handler smoke tests
tests/test_install_artifacts.py            launcher and routing-skill contract tests
tests/eval_cases.json                      sanitized synthetic QA evaluation inputs
tests/test_eval_cases.py                   deterministic evaluation gate
README.md                                  setup, operation, security, fallback, and removal instructions
```

---

## Phase 1 — Safe local core

### Task 1: Package foundation, configuration, and contracts

**Files:**
- Create: `pyproject.toml`
- Create: `src/qa_router_mcp/__init__.py`
- Create: `src/qa_router_mcp/config.py`
- Create: `src/qa_router_mcp/contracts.py`
- Test: `tests/test_config.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Consumes: environment variables prefixed with `QA_ROUTER_` only.
- Produces: `Settings.from_env() -> Settings`, `DraftKind`, `DraftEnvelope`, `LearningProposal`, `LearningEnvelope`, `ProposalStatus`.

- [ ] **Step 1: Write failing settings and contract tests**

```python
# tests/test_config.py
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


def test_non_loopback_or_unpinned_model_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="pinned model"):
        Settings(model="another-model")
    with pytest.raises(ValueError, match="loopback"):
        Settings(ollama_url="https://remote.example.test")
```

```python
# tests/test_contracts.py
import pytest
from pydantic import ValidationError

from qa_router_mcp.contracts import (
    DraftEnvelope,
    LearningEnvelope,
    LearningProposal,
    ProposalStatus,
)


def test_successful_draft_is_always_unverified():
    result = DraftEnvelope(draft="Case A", unverified=["Expected result"])
    assert result.status == "ok"
    assert result.unverified == ["Expected result"]


def test_successful_draft_requires_unverified_items():
    with pytest.raises(ValidationError):
        DraftEnvelope(draft="Case A", unverified=[])


def test_learning_proposal_starts_pending():
    proposal = LearningProposal(id="lp_123", text="Use Given/When/Then headings")
    assert proposal.status is ProposalStatus.PENDING


def test_learning_fallback_requires_reason():
    result = LearningEnvelope(status="fallback", reason="hermes_timeout")
    assert result.proposal is None
```

- [ ] **Step 2: Run tests and verify import failures**

Run: `uv run pytest tests/test_config.py tests/test_contracts.py -q`

Expected: FAIL because `qa_router_mcp.config` and `qa_router_mcp.contracts` do not exist.

- [ ] **Step 3: Add package metadata and minimal implementations**

```toml
# pyproject.toml
[project]
name = "qa-router-mcp"
version = "0.1.0"
description = "Safe local QA drafting and approved Hermes learning for Codex"
requires-python = ">=3.12"
dependencies = [
  "fastmcp>=3.3,<4.0",
  "httpx>=0.28,<1.0",
  "pydantic>=2.11,<3.0",
]

[project.scripts]
qa-router-mcp = "qa_router_mcp.server:main"

[dependency-groups]
dev = [
  "pytest>=8.3,<9.0",
  "pytest-asyncio>=0.26,<1.0",
  "ruff>=0.11,<1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

```python
# src/qa_router_mcp/__init__.py
__version__ = "0.1.0"
```

```python
# src/qa_router_mcp/config.py
from dataclasses import dataclass
from os import environ
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    enabled: bool = True
    model: str = "gemma4:12b-it-q4_K_M"
    ollama_url: str = "http://127.0.0.1:11434"
    context: int = 64_000
    max_output_tokens: int = 2_048
    max_input_chars: int = 40_000
    timeout_seconds: float = 45.0
    max_parallel: int = 1
    keep_alive: str = "5m"
    data_dir: Path = Path("/Users/andreiviarshko/.qa-router")
    hermes_command: Path = Path("/Users/andreiviarshko/.local/bin/qa-routine")

    def __post_init__(self) -> None:
        if self.model != "gemma4:12b-it-q4_K_M":
            raise ValueError("model must match the pinned model")
        if self.context != 64_000 or self.max_parallel != 1:
            raise ValueError("context and parallelism must match the verified profile")
        if not self.ollama_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Ollama URL must use loopback")

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        return cls(
            enabled=environ.get("QA_ROUTER_ENABLED", "1") == "1",
            model=environ.get("QA_ROUTER_MODEL", defaults.model),
            ollama_url=environ.get("QA_ROUTER_OLLAMA_URL", defaults.ollama_url),
            context=int(environ.get("QA_ROUTER_CONTEXT", str(defaults.context))),
            max_output_tokens=int(
                environ.get("QA_ROUTER_MAX_OUTPUT", str(defaults.max_output_tokens))
            ),
            max_input_chars=int(
                environ.get("QA_ROUTER_MAX_INPUT_CHARS", str(defaults.max_input_chars))
            ),
            timeout_seconds=float(
                environ.get("QA_ROUTER_TIMEOUT", str(defaults.timeout_seconds))
            ),
            max_parallel=1,
            keep_alive=environ.get("QA_ROUTER_KEEP_ALIVE", defaults.keep_alive),
            data_dir=Path(environ.get("QA_ROUTER_DATA_DIR", str(defaults.data_dir))),
            hermes_command=Path(
                environ.get("QA_ROUTER_HERMES", str(defaults.hermes_command))
            ),
        )
```

```python
# src/qa_router_mcp/contracts.py
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DraftKind(StrEnum):
    TEST_CASES = "test_cases"
    LOG_SUMMARY = "log_summary"
    AUTOMATION_SKELETON = "automation_skeleton"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class DraftEnvelope(BaseModel):
    status: Literal["ok", "refused", "fallback"] = "ok"
    draft: str = ""
    assumptions: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    learning_proposal: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "DraftEnvelope":
        if self.status == "ok" and (not self.draft.strip() or not self.unverified):
            raise ValueError("successful drafts require content and unverified items")
        if self.status != "ok" and not self.reason:
            raise ValueError("non-success results require a reason")
        return self


class LearningProposal(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=2_000)
    status: ProposalStatus = ProposalStatus.PENDING


class LearningEnvelope(BaseModel):
    status: Literal["approved", "fallback"]
    proposal: LearningProposal | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_learning_result(self) -> "LearningEnvelope":
        if self.status == "approved" and self.proposal is None:
            raise ValueError("approved result requires a proposal")
        if self.status == "fallback" and not self.reason:
            raise ValueError("fallback result requires a reason")
        return self
```

- [ ] **Step 4: Sync and verify the foundation**

Run: `uv sync && uv run pytest tests/test_config.py tests/test_contracts.py -q && uv run ruff check .`

Expected: all tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the foundation**

```bash
git add pyproject.toml uv.lock src/qa_router_mcp tests/test_config.py tests/test_contracts.py
git commit -m "feat: add router contracts and configuration"
```

### Task 2: Data policy and deterministic sanitization

**Files:**
- Create: `src/qa_router_mcp/policy.py`
- Test: `tests/test_policy.py`

**Interfaces:**
- Consumes: `DraftKind`, raw transient input, and proposal text.
- Produces: `PolicyError(code: str)`, `sanitize_transient(text: str, limit: int) -> str`, `validate_learning_text(text: str) -> str`, `assert_allowed_request(kind: DraftKind, text: str) -> None`.

- [ ] **Step 1: Write failing policy tests**

```python
# tests/test_policy.py
import pytest

from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.policy import (
    PolicyError,
    assert_allowed_request,
    sanitize_transient,
    validate_learning_text,
)


def test_transient_identifiers_are_replaced():
    raw = "ABC-123 at https://stage.example.test by qa@example.test commit deadbee"
    assert sanitize_transient(raw, 1_000) == (
        "[ISSUE] at [URL] by [EMAIL] commit [COMMIT]"
    )


@pytest.mark.parametrize(
    "raw",
    ["Authorization: Bearer secret-value", "password=hunter2", "api_key: abc123"],
)
def test_secret_like_input_is_rejected(raw):
    with pytest.raises(PolicyError, match="secret_detected"):
        sanitize_transient(raw, 1_000)


def test_oversized_input_is_rejected():
    with pytest.raises(PolicyError, match="input_too_large"):
        sanitize_transient("x" * 11, 10)


def test_decision_request_is_refused():
    with pytest.raises(PolicyError, match="codex_only_decision"):
        assert_allowed_request(DraftKind.TEST_CASES, "Determine release readiness")


def test_learning_text_rejects_corporate_artifacts():
    for text in (
        "Remember ABC-123",
        "Use feature/login-rework",
        "Copy src/project/private.py",
        "Read /Users/me/company/repo",
    ):
        with pytest.raises(PolicyError, match="learning_content_forbidden"):
            validate_learning_text(text)
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `uv run pytest tests/test_policy.py -q`

Expected: FAIL because `qa_router_mcp.policy` does not exist.

- [ ] **Step 3: Implement explicit rejection and replacement rules**

```python
# src/qa_router_mcp/policy.py
import re

from qa_router_mcp.contracts import DraftKind


class PolicyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer|password|api[_-]?key|access[_-]?token|cookie)"
    r"\s*[:=]?\s*\S+"
)
DECISION = re.compile(
    r"(?i)\b(decide|determine|choose|assess)\b.{0,32}"
    r"\b(severity|priority|release readiness|merge readiness|root cause)\b"
)
REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"https?://[^\s]+"), "[URL]"),
    (re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b"), "[ISSUE]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"(?<![0-9a-f])\b[0-9a-f]{7,40}\b(?![0-9a-f])", re.I), "[COMMIT]"),
    (re.compile(r"/(?:Users|home|var|opt)/[^\s]+"), "[PATH]"),
    (re.compile(r"\b(?:feature|bugfix|hotfix|release)/[\w.-]+\b", re.I), "[BRANCH]"),
    (re.compile(r"\b(?:src|tests?|packages?|apps?|lib)/[\w./-]+\b", re.I), "[PATH]"),
)


def sanitize_transient(text: str, limit: int) -> str:
    if len(text) > limit:
        raise PolicyError("input_too_large")
    if SECRET.search(text):
        raise PolicyError("secret_detected")
    clean = text
    for pattern, replacement in REPLACEMENTS:
        clean = pattern.sub(replacement, clean)
    return clean.strip()


def assert_allowed_request(kind: DraftKind, text: str) -> None:
    del kind
    if DECISION.search(text):
        raise PolicyError("codex_only_decision")


def validate_learning_text(text: str) -> str:
    if SECRET.search(text) or any(pattern.search(text) for pattern, _ in REPLACEMENTS):
        raise PolicyError("learning_content_forbidden")
    clean = text.strip()
    if not clean or len(clean) > 2_000:
        raise PolicyError("learning_content_forbidden")
    return clean
```

- [ ] **Step 4: Run policy and full unit checks**

Run: `uv run pytest tests/test_policy.py -q && uv run ruff check src/qa_router_mcp/policy.py tests/test_policy.py`

Expected: all policy tests pass and Ruff reports no errors.

- [ ] **Step 5: Commit the policy boundary**

```bash
git add src/qa_router_mcp/policy.py tests/test_policy.py
git commit -m "feat: enforce local data policy"
```

### Task 3: Direct Ollama drafting and isolated Hermes learning adapters

**Files:**
- Create: `src/qa_router_mcp/backends.py`
- Test: `tests/test_backends.py`

**Interfaces:**
- Consumes: `Settings`, a prompt string, `DraftEnvelope.model_json_schema()`, and validated learning text.
- Produces: `DraftBackend.generate(prompt: str) -> DraftEnvelope`, `LearningBackend.apply(text: str) -> str`, `OllamaDraftBackend`, `HermesLearningBackend`, `BackendError(code: str)`.

- [ ] **Step 1: Write failing adapter tests with fake HTTP and subprocess boundaries**

```python
# tests/test_backends.py
from pathlib import Path

import httpx
import pytest

from qa_router_mcp.backends import HermesLearningBackend, OllamaDraftBackend
from qa_router_mcp.config import Settings


@pytest.mark.asyncio
async def test_ollama_uses_direct_structured_request():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["model"] == "gemma4:12b-it-q4_K_M"
        assert body["options"]["num_ctx"] == 64_000
        assert body["stream"] is False
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
        "/safe/qa-routine", "--reasoning", "none", "--toolsets", "memory"
    )
    assert "Use concise case titles" in captured["args"][-1]
    assert set(captured["env"]) == {"HOME", "PATH", "HERMES_PROFILE"}
```

- [ ] **Step 2: Run adapter tests and verify failure**

Run: `uv run pytest tests/test_backends.py -q`

Expected: FAIL because the backend classes do not exist.

- [ ] **Step 3: Implement one direct HTTP call and one constrained subprocess call**

```python
# src/qa_router_mcp/backends.py
import asyncio
import json
import os
from typing import Protocol

import httpx

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope


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
                response = await self.client.post(f"{self.settings.ollama_url}/api/chat", json=payload)
                response.raise_for_status()
            return DraftEnvelope.model_validate_json(response.json()["message"]["content"])
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, ValueError) as exc:
            raise BackendError("ollama_invalid_response") from exc


class HermesLearningBackend:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def apply(self, text: str) -> str:
        prompt = (
            "Store this user-approved generic QA preference using the memory tool. "
            "Do not create or edit skills, infer project facts, or rewrite the text:\n" + text
        )
        env = {
            "HOME": "/Users/andreiviarshko",
            "PATH": "/Users/andreiviarshko/.local/bin:/opt/homebrew/bin:/usr/bin:/bin",
            "HERMES_PROFILE": "qa-routine",
        }
        process = await asyncio.create_subprocess_exec(
            str(self.settings.hermes_command),
            "--reasoning", "none",
            "--toolsets", "memory",
            "--ignore-rules",
            "--oneshot", prompt,
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
```

- [ ] **Step 4: Verify adapters and lint**

Run: `uv run pytest tests/test_backends.py -q && uv run ruff check src/qa_router_mcp/backends.py tests/test_backends.py`

Expected: tests pass; no prompt or response is printed by production code.

- [ ] **Step 5: Commit backend boundaries**

```bash
git add src/qa_router_mcp/backends.py tests/test_backends.py
git commit -m "feat: add isolated local model backends"
```

### Task 4: Sanitized learning proposal store

**Files:**
- Create: `src/qa_router_mcp/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `LearningProposal`, validated text, and `Settings.data_dir`.
- Produces: `ProposalStore.add(text) -> LearningProposal`, `.list_pending() -> list[LearningProposal]`, `.get_pending(id) -> LearningProposal`, `.approve(id) -> LearningProposal`, `.reject(id) -> bool`.

- [ ] **Step 1: Write failing proposal lifecycle tests**

```python
# tests/test_store.py
import json

import pytest

from qa_router_mcp.policy import PolicyError
from qa_router_mcp.store import ProposalStore


def test_pending_approve_and_reject_lifecycle(tmp_path):
    store = ProposalStore(tmp_path)
    first = store.add("Use concise case titles")
    second = store.add("Separate assumptions")
    assert [item.id for item in store.list_pending()] == [first.id, second.id]
    assert store.get_pending(first.id).text == "Use concise case titles"
    approved = store.approve(first.id)
    assert approved.status == "approved"
    assert store.reject(second.id) is True
    assert store.list_pending() == []
    saved = json.loads((tmp_path / "proposals.json").read_text())
    assert saved["approved"][0]["text"] == "Use concise case titles"


def test_forbidden_text_is_never_written(tmp_path):
    store = ProposalStore(tmp_path)
    with pytest.raises(PolicyError):
        store.add("Remember ABC-123")
    assert not (tmp_path / "proposals.json").exists()
```

- [ ] **Step 2: Run store tests and verify failure**

Run: `uv run pytest tests/test_store.py -q`

Expected: FAIL because `ProposalStore` does not exist.

- [ ] **Step 3: Implement atomic JSON persistence with opaque IDs**

```python
# src/qa_router_mcp/store.py
import json
import os
import secrets
from pathlib import Path

from qa_router_mcp.contracts import LearningProposal, ProposalStatus
from qa_router_mcp.policy import validate_learning_text


class ProposalStore:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "proposals.json"

    def _load(self) -> dict[str, list[dict[str, str]]]:
        if not self.path.exists():
            return {"pending": [], "approved": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, list[dict[str, str]]]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def add(self, text: str) -> LearningProposal:
        proposal = LearningProposal(id=f"lp_{secrets.token_hex(8)}", text=validate_learning_text(text))
        data = self._load()
        data["pending"].append(proposal.model_dump(mode="json"))
        self._save(data)
        return proposal

    def list_pending(self) -> list[LearningProposal]:
        return [LearningProposal.model_validate(item) for item in self._load()["pending"]]

    def get_pending(self, proposal_id: str) -> LearningProposal:
        match = next(
            (item for item in self._load()["pending"] if item["id"] == proposal_id), None
        )
        if match is None:
            raise KeyError("proposal_not_found")
        return LearningProposal.model_validate(match)

    def approve(self, proposal_id: str) -> LearningProposal:
        data = self._load()
        match = next((item for item in data["pending"] if item["id"] == proposal_id), None)
        if match is None:
            raise KeyError("proposal_not_found")
        data["pending"] = [item for item in data["pending"] if item["id"] != proposal_id]
        approved = LearningProposal.model_validate(match).model_copy(
            update={"status": ProposalStatus.APPROVED}
        )
        data["approved"].append(approved.model_dump(mode="json"))
        self._save(data)
        return approved

    def reject(self, proposal_id: str) -> bool:
        data = self._load()
        remaining = [item for item in data["pending"] if item["id"] != proposal_id]
        found = len(remaining) != len(data["pending"])
        if found:
            data["pending"] = remaining
            self._save(data)
        return found
```

- [ ] **Step 4: Verify lifecycle, permissions, and full core suite**

Run: `uv run pytest tests/test_store.py tests/test_policy.py -q && uv run ruff check .`

Expected: all tests pass; the persisted file mode is `0600` on macOS.

- [ ] **Step 5: Commit the proposal store**

```bash
git add src/qa_router_mcp/store.py tests/test_store.py
git commit -m "feat: add approved learning queue"
```

## Phase 2 — One-chat orchestration

### Task 5: Prompt construction and router service

**Files:**
- Create: `src/qa_router_mcp/prompts.py`
- Create: `src/qa_router_mcp/events.py`
- Create: `src/qa_router_mcp/service.py`
- Test: `tests/test_service.py`

**Interfaces:**
- Consumes: `DraftBackend`, `LearningBackend`, `ProposalStore`, `Settings`, `DraftKind`, and raw tool fields.
- Produces: `JsonEventSink.emit(tool, outcome, duration_ms, error_category)`, `RouterService.draft(kind, content, pattern=None) -> DraftEnvelope`, `.list_proposals()`, `.approve_proposal(id) -> LearningEnvelope`, `.reject_proposal(id)`.

- [ ] **Step 1: Write failing service tests with deterministic fakes**

```python
# tests/test_service.py
import pytest

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


class DraftFake:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return self.result


class LearningFake:
    def __init__(self):
        self.texts = []

    async def apply(self, text):
        self.texts.append(text)
        return "stored"


@pytest.mark.asyncio
async def test_draft_sanitizes_and_queues_safe_learning(tmp_path):
    draft = DraftFake(DraftEnvelope(
        draft="Case", unverified=["Expected result"],
        learning_proposal="Use concise case titles",
    ))
    service = RouterService(Settings(data_dir=tmp_path), draft, LearningFake(), ProposalStore(tmp_path))
    result = await service.draft(DraftKind.TEST_CASES, "ABC-123 at https://stage.test")
    assert result.status == "ok"
    assert "ABC-123" not in draft.prompts[0]
    assert len(service.list_proposals()) == 1


@pytest.mark.asyncio
async def test_policy_failure_returns_refusal_without_backend_call(tmp_path):
    draft = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    service = RouterService(Settings(data_dir=tmp_path), draft, LearningFake(), ProposalStore(tmp_path))
    result = await service.draft(DraftKind.TEST_CASES, "password=secret")
    assert result.status == "refused"
    assert result.reason == "secret_detected"
    assert draft.prompts == []


@pytest.mark.asyncio
async def test_approval_sends_only_stored_validated_text(tmp_path):
    learning = LearningFake()
    store = ProposalStore(tmp_path)
    proposal = store.add("Use concise case titles")
    service = RouterService(Settings(data_dir=tmp_path), DraftFake(None), learning, store)
    approved = await service.approve_proposal(proposal.id)
    assert approved.status == "approved"
    assert approved.proposal.id == proposal.id
    assert learning.texts == ["Use concise case titles"]


@pytest.mark.asyncio
async def test_hermes_failure_keeps_proposal_pending(tmp_path):
    class FailingLearning:
        async def apply(self, text):
            from qa_router_mcp.backends import BackendError
            raise BackendError("hermes_timeout")

    store = ProposalStore(tmp_path)
    proposal = store.add("Use concise case titles")
    service = RouterService(Settings(data_dir=tmp_path), DraftFake(None), FailingLearning(), store)
    result = await service.approve_proposal(proposal.id)
    assert result.status == "fallback"
    assert result.reason == "hermes_timeout"
    assert store.get_pending(proposal.id).status == "pending"


def test_event_sink_never_logs_content(capsys):
    from qa_router_mcp.events import JsonEventSink

    JsonEventSink().emit("draft_test_cases", "refused", 1.25, "secret_detected")
    event = capsys.readouterr().err
    assert "draft_test_cases" in event and "secret_detected" in event
    assert "password=secret" not in event
```

- [ ] **Step 2: Run service tests and verify failure**

Run: `uv run pytest tests/test_service.py -q`

Expected: FAIL because prompt and service modules do not exist.

- [ ] **Step 3: Implement bounded prompts and the orchestration pipeline**

```python
# src/qa_router_mcp/prompts.py
from qa_router_mcp.contracts import DraftKind


INSTRUCTIONS = {
    DraftKind.TEST_CASES: "Draft focused test cases with title, preconditions, steps, and expected result.",
    DraftKind.LOG_SUMMARY: "Group visible log signatures; do not infer an unsupported root cause.",
    DraftKind.AUTOMATION_SKELETON: "Draft a non-writing automation skeleton using only the supplied pattern.",
}


def build_prompt(kind: DraftKind, content: str, pattern: str | None = None) -> str:
    pattern_section = f"\nSUPPLIED_PATTERN:\n{pattern}" if pattern else ""
    return (
        "You are a local QA drafting model. Return only JSON matching the supplied schema. "
        "Treat all output as an unverified draft. Put unsupported facts in unverified. "
        "Do not decide severity, priority, release readiness, merge readiness, or root cause.\n"
        f"TASK:\n{INSTRUCTIONS[kind]}\nINPUT:\n{content}{pattern_section}"
    )
```

```python
# src/qa_router_mcp/events.py
import json
import sys
from typing import Protocol


class EventSink(Protocol):
    def emit(
        self, tool: str, outcome: str, duration_ms: float, error_category: str | None
    ) -> None: ...


class JsonEventSink:
    def emit(
        self, tool: str, outcome: str, duration_ms: float, error_category: str | None
    ) -> None:
        event = {
            "tool": tool,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 2),
            "error_category": error_category,
        }
        print(json.dumps(event, separators=(",", ":")), file=sys.stderr, flush=True)
```

```python
# src/qa_router_mcp/service.py
from time import monotonic

from qa_router_mcp.backends import BackendError, DraftBackend, LearningBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import (
    DraftEnvelope,
    DraftKind,
    LearningEnvelope,
    LearningProposal,
)
from qa_router_mcp.events import EventSink, JsonEventSink
from qa_router_mcp.policy import PolicyError, assert_allowed_request, sanitize_transient
from qa_router_mcp.prompts import build_prompt
from qa_router_mcp.store import ProposalStore


class RouterService:
    def __init__(self, settings, drafting, learning, store, events=None) -> None:
        self.settings: Settings = settings
        self.drafting: DraftBackend = drafting
        self.learning: LearningBackend = learning
        self.store: ProposalStore = store
        self.events: EventSink = events or JsonEventSink()

    def _record(self, kind: DraftKind, result: DraftEnvelope, started: float) -> DraftEnvelope:
        self.events.emit(
            kind.value,
            result.status,
            (monotonic() - started) * 1_000,
            result.reason,
        )
        return result

    async def draft(self, kind: DraftKind, content: str, pattern: str | None = None) -> DraftEnvelope:
        started = monotonic()
        if not self.settings.enabled:
            result = DraftEnvelope(status="fallback", reason="local_delegation_disabled")
            return self._record(kind, result, started)
        try:
            packet = content if pattern is None else f"{content}\n{pattern}"
            assert_allowed_request(kind, packet)
            if len(packet) > self.settings.max_input_chars:
                raise PolicyError("input_too_large")
            safe_content = sanitize_transient(content, self.settings.max_input_chars)
            safe_pattern = (
                sanitize_transient(pattern, self.settings.max_input_chars) if pattern else None
            )
            result = await self.drafting.generate(build_prompt(kind, safe_content, safe_pattern))
            if result.learning_proposal:
                try:
                    self.store.add(result.learning_proposal)
                except PolicyError:
                    result.learning_proposal = None
            return self._record(kind, result, started)
        except PolicyError as exc:
            result = DraftEnvelope(status="refused", reason=exc.code)
            return self._record(kind, result, started)
        except BackendError as exc:
            result = DraftEnvelope(status="fallback", reason=exc.code)
            return self._record(kind, result, started)

    def list_proposals(self) -> list[LearningProposal]:
        return self.store.list_pending()

    async def approve_proposal(self, proposal_id: str) -> LearningEnvelope:
        proposal = self.store.get_pending(proposal_id)
        try:
            await self.learning.apply(proposal.text)
        except BackendError as exc:
            return LearningEnvelope(status="fallback", reason=exc.code)
        approved = self.store.approve(proposal_id)
        return LearningEnvelope(status="approved", proposal=approved)

    def reject_proposal(self, proposal_id: str) -> bool:
        return self.store.reject(proposal_id)
```

- [ ] **Step 4: Add one-repair behavior and verify it explicitly**

Remove the now-unused `json` import, import `ValidationError` from Pydantic, and replace `OllamaDraftBackend.generate` with these two methods:

```python
async def _request(self, payload: dict[str, object]) -> str:
    try:
        async with self._gate:
            response = await self.client.post(
                f"{self.settings.ollama_url}/api/chat", json=payload
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
            messages.append({
                "role": "user",
                "content": "Return valid JSON only. Keep every unsupported statement in unverified.",
            })
    raise BackendError("ollama_invalid_schema")
```

Add this exact regression test:

```python
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
```

Run: `uv run pytest tests/test_backends.py tests/test_service.py -q && uv run ruff check .`

Expected: all tests pass and the invalid response produces exactly one repair call.

- [ ] **Step 5: Commit service orchestration**

```bash
git add src/qa_router_mcp/prompts.py src/qa_router_mcp/events.py src/qa_router_mcp/service.py tests/test_service.py tests/test_backends.py
git commit -m "feat: orchestrate safe QA drafting"
```

### Task 6: FastMCP tools and STDIO entry point

**Files:**
- Create: `src/qa_router_mcp/server.py`
- Create: `src/qa_router_mcp/__main__.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `RouterService` and all six tool argument sets.
- Produces: `build_server(service: RouterService) -> FastMCP` and `main() -> None` with tools `draft_test_cases`, `summarize_logs`, `draft_automation_skeleton`, `list_learning_proposals`, `approve_learning_proposal`, `reject_learning_proposal`.

- [ ] **Step 1: Write failing tool-registration and handler tests**

```python
# tests/test_server.py
import pytest
from fastmcp import Client

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope
from qa_router_mcp.server import build_server
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


class DraftFake:
    async def generate(self, prompt):
        return DraftEnvelope(draft="Case", unverified=["Review locally"])


class LearningFake:
    async def apply(self, text):
        return "stored"


@pytest.mark.asyncio
async def test_server_exposes_only_six_narrow_tools(tmp_path):
    service = RouterService(
        Settings(data_dir=tmp_path), DraftFake(), LearningFake(), ProposalStore(tmp_path)
    )
    async with Client(build_server(service)) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert names == {
            "draft_test_cases", "summarize_logs", "draft_automation_skeleton",
            "list_learning_proposals", "approve_learning_proposal", "reject_learning_proposal",
        }
        result = await client.call_tool("draft_test_cases", {"requirement": "Guest checkout"})
        assert result.structured_content["status"] == "ok"
        refusal = await client.call_tool(
            "approve_learning_proposal",
            {"proposal_id": "lp_missing", "user_confirmed": False},
        )
        assert refusal.structured_content["reason"] == "explicit_approval_required"
```

- [ ] **Step 2: Run server test and verify failure**

Run: `uv run pytest tests/test_server.py -q`

Expected: FAIL because `build_server` does not exist.

- [ ] **Step 3: Register only the approved FastMCP tools**

```python
# src/qa_router_mcp/server.py
from fastmcp import FastMCP

from qa_router_mcp.backends import HermesLearningBackend, OllamaDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind, LearningEnvelope, LearningProposal
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


def build_server(service: RouterService) -> FastMCP:
    mcp = FastMCP(name="qa-router-mcp")

    @mcp.tool
    async def draft_test_cases(requirement: str, examples: str = "") -> DraftEnvelope:
        """Draft focused unverified test cases from a bounded sanitized requirement."""
        content = requirement if not examples else f"{requirement}\nEXAMPLES:\n{examples}"
        return await service.draft(DraftKind.TEST_CASES, content)

    @mcp.tool
    async def summarize_logs(logs: str) -> DraftEnvelope:
        """Group sanitized log fragments by visible signature without root-cause decisions."""
        return await service.draft(DraftKind.LOG_SUMMARY, logs)

    @mcp.tool
    async def draft_automation_skeleton(scenario: str, pattern: str) -> DraftEnvelope:
        """Draft a non-writing automation skeleton from an explicit supplied pattern."""
        return await service.draft(DraftKind.AUTOMATION_SKELETON, scenario, pattern)

    @mcp.tool
    def list_learning_proposals() -> list[LearningProposal]:
        """List sanitized pending proposals for explicit user review."""
        return service.list_proposals()

    @mcp.tool
    async def approve_learning_proposal(
        proposal_id: str, user_confirmed: bool
    ) -> LearningEnvelope:
        """Approve one reviewed proposal and send only its validated text to Hermes."""
        if not user_confirmed:
            return LearningEnvelope(status="fallback", reason="explicit_approval_required")
        return await service.approve_proposal(proposal_id)

    @mcp.tool
    def reject_learning_proposal(proposal_id: str) -> bool:
        """Delete one pending proposal without sending it to Hermes."""
        return service.reject_proposal(proposal_id)

    return mcp


def main() -> None:
    settings = Settings.from_env()
    service = RouterService(
        settings,
        OllamaDraftBackend(settings),
        HermesLearningBackend(settings),
        ProposalStore(settings.data_dir),
    )
    build_server(service).run()
```

```python
# src/qa_router_mcp/__main__.py
from qa_router_mcp.server import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify tools through the in-memory MCP transport**

Run: `uv run pytest tests/test_server.py -q && uv run python -c 'from qa_router_mcp.server import main; assert callable(main)'`

Expected: the MCP test passes and the stdio entry point imports without starting a blocking process.

- [ ] **Step 5: Commit the MCP interface**

```bash
git add src/qa_router_mcp/server.py src/qa_router_mcp/__main__.py tests/test_server.py
git commit -m "feat: expose safe QA router tools"
```

## Phase 3 — Codex integration and acceptance

### Task 7: Clean launcher and automatic Codex routing skill

**Files:**
- Create: `scripts/qa-router-mcp`
- Create: `codex/skills/qa-local-routing/SKILL.md`
- Test: `tests/test_install_artifacts.py`
- Modify after tests and explicit approval: `/Users/andreiviarshko/.codex/config.toml`
- Create after tests and explicit approval: `/Users/andreiviarshko/.codex/skills/qa-local-routing/SKILL.md`

**Interfaces:**
- Consumes: `/opt/homebrew/bin/uv`, the repository path, Ollama on loopback, and Codex MCP configuration.
- Produces: a credential-clean server process and a routing skill that keeps final decisions in Codex.

- [ ] **Step 1: Write failing artifact contract tests**

```python
# tests/test_install_artifacts.py
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_launcher_clears_inherited_environment():
    text = (ROOT / "scripts/qa-router-mcp").read_text()
    assert "/usr/bin/env -i" in text
    assert "QA_ROUTER_ENABLED=1" in text
    assert "exec /opt/homebrew/bin/uv run" in text
    assert "TOKEN" not in text and "PASSWORD" not in text


def test_skill_preserves_codex_authority_and_hermes_boundary():
    text = (ROOT / "codex/skills/qa-local-routing/SKILL.md").read_text()
    assert "Gemma" in text
    assert "explicit user approval" in text
    assert "Never send transient task content to Hermes" in text
    assert "Codex remains responsible" in text
```

- [ ] **Step 2: Run artifact tests and verify missing files**

Run: `uv run pytest tests/test_install_artifacts.py -q`

Expected: FAIL because the launcher and skill do not exist.

- [ ] **Step 3: Create the clean launcher and routing skill**

```sh
#!/bin/sh
exec /usr/bin/env -i \
  HOME=/Users/andreiviarshko \
  PATH=/Users/andreiviarshko/.local/bin:/opt/homebrew/bin:/usr/bin:/bin \
  QA_ROUTER_ENABLED=1 \
  QA_ROUTER_MODEL=gemma4:12b-it-q4_K_M \
  QA_ROUTER_CONTEXT=64000 \
  QA_ROUTER_DATA_DIR=/Users/andreiviarshko/.qa-router \
  QA_ROUTER_HERMES=/Users/andreiviarshko/.local/bin/qa-routine \
  /opt/homebrew/bin/uv run --directory /Users/andreiviarshko/Projects/qa-router-mcp qa-router-mcp
```

```markdown
---
name: qa-local-routing
description: Use for routine QA drafting in Codex when a bounded sanitized packet is sufficient: focused test-case drafts, visible log-signature grouping, or a non-writing automation skeleton from an explicit pattern.
---

# QA Local Routing

1. Codex remains responsible for evidence gathering, Jira/MR/diff analysis, CodeGraph navigation, final coverage, severity, release readiness, code changes, and every external-system action.
2. Use `draft_test_cases`, `summarize_logs`, or `draft_automation_skeleton` only after selecting the smallest relevant input packet.
3. Never include credentials, cookies, tokens, personal/payment data, complete repositories, or unrestricted corporate documents.
4. Treat every local result as a draft. Verify its `assumptions` and `unverified` items before using it.
5. Never send transient task content to Hermes. Gemma handles drafts directly.
6. Show a learning proposal only when it is generic and useful. Call `approve_learning_proposal` only after explicit user approval; otherwise leave it pending or reject it.
7. If the router refuses, times out, or falls back, continue in Codex without blocking the user.
```

Run: `chmod 755 scripts/qa-router-mcp && uv run pytest tests/test_install_artifacts.py -q`

Expected: both artifact tests pass.

- [ ] **Step 4: Install with backup, explicit approval, and read-back**

Before changing the user configuration, request approval for writes outside the repository. After approval:

```bash
cp /Users/andreiviarshko/.codex/config.toml /Users/andreiviarshko/.codex/config.toml.qa-router-backup-20260830
mkdir -p /Users/andreiviarshko/.codex/skills/qa-local-routing
cp codex/skills/qa-local-routing/SKILL.md /Users/andreiviarshko/.codex/skills/qa-local-routing/SKILL.md
```

Add this exact TOML block once to `/Users/andreiviarshko/.codex/config.toml` using `apply_patch`:

```toml
[mcp_servers.qa-router]
command = "/Users/andreiviarshko/Projects/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 60
```

Read back only the new MCP block and installed skill header. Expected: paths match the repository and no credential environment entries are present.

- [ ] **Step 5: Commit repository-owned integration artifacts**

```bash
git add scripts/qa-router-mcp codex/skills/qa-local-routing/SKILL.md tests/test_install_artifacts.py
git commit -m "feat: add Codex local routing integration"
```

### Task 8: Synthetic evaluation, operational documentation, and release gate

**Files:**
- Create: `tests/eval_cases.json`
- Create: `tests/test_eval_cases.py`
- Create: `README.md`

**Interfaces:**
- Consumes: the six MCP tools, fake backends, local Ollama, the `qa-routine` profile, and the verified benchmark settings.
- Produces: deterministic policy coverage, a documented live smoke test, disable/removal steps, and a release decision based on measured evidence.

- [ ] **Step 1: Add a failing deterministic evaluation set**

```json
[
  {"name":"case_draft","kind":"test_cases","input":"Guest can submit checkout","expected":"ok"},
  {"name":"checklist","kind":"test_cases","input":"Normalize a three-item smoke checklist","expected":"ok"},
  {"name":"duplicate_case","kind":"test_cases","input":"Find duplicate wording in two synthetic cases","expected":"ok"},
  {"name":"log_group","kind":"log_summary","input":"ERROR timeout\nERROR timeout\nWARN retry","expected":"ok"},
  {"name":"wdio_skeleton","kind":"automation_skeleton","input":"Verify login redirect","pattern":"describe/it page-object pattern","expected":"ok"},
  {"name":"severity","kind":"test_cases","input":"Determine severity for checkout failure","expected":"refused"},
  {"name":"secret","kind":"log_summary","input":"Authorization: Bearer secret-value","expected":"refused"},
  {"name":"forbidden_learning","kind":"test_cases","input":"Draft concise generic cases","expected":"ok","proposal":"Remember ABC-123"},
  {"name":"outage","kind":"test_cases","input":"Guest checkout","expected":"fallback","backend_error":"ollama_invalid_response"}
]
```

```python
# tests/test_eval_cases.py
import json
from pathlib import Path

import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


CASES = json.loads((Path(__file__).parent / "eval_cases.json").read_text())


class EvalDraftBackend:
    def __init__(self, case):
        self.case = case

    async def generate(self, prompt):
        if code := self.case.get("backend_error"):
            raise BackendError(code)
        return DraftEnvelope(
            draft="Synthetic draft",
            unverified=["Codex review required"],
            learning_proposal=self.case.get("proposal"),
        )


class EvalLearningBackend:
    async def apply(self, text):
        return "stored"


def test_eval_set_contains_required_policy_and_fallback_categories():
    assert len(CASES) == 9
    assert {case["expected"] for case in CASES} == {"ok", "refused", "fallback"}
    assert {case["name"] for case in CASES} == {
        "case_draft", "checklist", "duplicate_case", "log_group", "wdio_skeleton",
        "severity", "secret", "forbidden_learning", "outage",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
async def test_synthetic_eval_case(case, tmp_path):
    store = ProposalStore(tmp_path / case["name"])
    service = RouterService(
        Settings(data_dir=tmp_path / case["name"]),
        EvalDraftBackend(case),
        EvalLearningBackend(),
        store,
    )
    result = await service.draft(
        DraftKind(case["kind"]), case["input"], case.get("pattern")
    )
    assert result.status == case["expected"]
    if case["name"] == "forbidden_learning":
        assert result.learning_proposal is None
        assert store.list_pending() == []
```

- [ ] **Step 2: Run the evaluation contract and full automated suite**

Run: `uv run pytest -q && uv run ruff check .`

Expected: all nine evaluation paths and the full automated suite pass.

- [ ] **Step 3: Write operational documentation with exact commands**

Document these sections in `README.md`:

```markdown
# QA Router MCP

## Data boundary
Drafts go directly to loopback Ollama. Hermes receives only explicitly approved, sanitized reusable learning text. Codex remains responsible for evidence and final decisions.

The router rejects secret-like input, replaces issue keys, URLs, emails, commit hashes, and local paths, and accepts at most 40,000 characters per field. Pending and approved proposals are stored in `/Users/andreiviarshko/.qa-router/proposals.json` with mode `0600`. Prompts, generated drafts, proposal text, and rejected content are never written to router logs.

## Tools
- `draft_test_cases`: focused unverified case drafts.
- `summarize_logs`: grouping by visible signature without root-cause claims.
- `draft_automation_skeleton`: non-writing skeleton from a supplied pattern.
- `list_learning_proposals`: sanitized pending proposals.
- `approve_learning_proposal`: explicit promotion and sanitized Hermes learning.
- `reject_learning_proposal`: deletion without a Hermes call.

## Fallback
`local_delegation_disabled`, `ollama_invalid_response`, `ollama_invalid_schema`, `hermes_timeout`, `hermes_failed`, and `explicit_approval_required` return control to Codex. Invalid model JSON receives exactly one repair request.

## Verify
`uv sync`
`uv run pytest -q`
`uv run ruff check .`
`ollama ps`

The verified M5 Pro baseline uses Ollama 0.33.0, Hermes 0.20.6, Gemma `gemma4:12b-it-q4_K_M`, 64K context, flash attention, q8_0 KV cache, and one parallel request. It showed zero swap, roughly 35–39% free-memory headroom while loaded, 1.5 seconds warm Hermes latency, and 16.1 seconds for a cold three-case draft.

## Disable
Set `QA_ROUTER_ENABLED=0` in `scripts/qa-router-mcp`, then restart Codex Desktop. Corporate MCP servers remain unchanged.

## Remove
Restore `/Users/andreiviarshko/.codex/config.toml.qa-router-backup-20260830`, remove `/Users/andreiviarshko/.codex/skills/qa-local-routing`, and restart Codex Desktop. The repository and `/Users/andreiviarshko/.qa-router` remain available for manual inspection.
```

- [ ] **Step 4: Run the live acceptance gate without corporate data**

1. Start Ollama with `OLLAMA_CONTEXT_LENGTH=64000`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, and `OLLAMA_NUM_PARALLEL=1`.
2. Restart Codex Desktop and verify the `qa-router` MCP exposes exactly six tools.
3. Call `draft_test_cases` with `Guest checkout supports an expired-card validation example`; require `status=ok`, non-empty `draft`, and non-empty `unverified`.
4. Submit `Authorization: Bearer synthetic-secret`; require `status=refused` and `reason=secret_detected`, with no backend request recorded.
5. Approve one generic synthetic proposal only after explicit confirmation; verify Hermes receives that text and no task content, then verify macOS swap does not grow materially during the representative request.

Expected: all five checks pass. If Ollama or Hermes is stopped, the corresponding tool returns `fallback` instead of blocking Codex.

- [ ] **Step 5: Final verification and commit**

Run: `uv run pytest -q && uv run ruff check . && git diff --check && git status --short`

Expected: tests and lint pass, `git diff --check` is clean, and only the evaluation/documentation files are uncommitted.

```bash
git add tests/eval_cases.json tests/test_eval_cases.py README.md
git commit -m "test: add QA router acceptance gate"
```

After the commit, run `git status --short`; expected output is empty.
