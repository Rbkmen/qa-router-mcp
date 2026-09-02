import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from qa_router_mcp.contracts import CanaryFeedbackReceipt, GenerationStats

CANARY_TARGET = 50


class EventSink(Protocol):
    def emit(
        self,
        tool: str,
        outcome: str,
        duration_ms: float,
        error_category: str | None,
        input_chars: int = 0,
        stats: GenerationStats | None = None,
        validation_repair: bool = False,
        *,
        model: str = "unknown",
        profile_version: str = "legacy",
        source: str = "legacy",
        estimated_prompt_tokens: int = 0,
        context_tokens: int = 0,
    ) -> None: ...

    @property
    def canary_active(self) -> bool: ...

    def record_feedback(
        self,
        tool: str,
        verdict: str,
        reason: str,
        *,
        profile_version: str,
    ) -> CanaryFeedbackReceipt: ...


class JsonEventSink:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._feedback_count = self._count_existing_feedback()

    @property
    def canary_active(self) -> bool:
        return self._feedback_count < CANARY_TARGET

    def emit(
        self,
        tool: str,
        outcome: str,
        duration_ms: float,
        error_category: str | None,
        input_chars: int = 0,
        stats: GenerationStats | None = None,
        validation_repair: bool = False,
        *,
        model: str = "unknown",
        profile_version: str = "legacy",
        source: str = "legacy",
        estimated_prompt_tokens: int = 0,
        context_tokens: int = 0,
    ) -> None:
        usage = stats or GenerationStats()
        event = {
            "schema_version": 2,
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool,
            "model": model,
            "profile_version": profile_version,
            "source": source,
            "outcome": outcome,
            "next_route": "local_draft" if outcome == "ok" else "terra",
            "duration_ms": round(duration_ms, 2),
            "error_category": error_category,
            "input_chars": input_chars,
            "estimated_prompt_tokens": estimated_prompt_tokens,
            "context_tokens": context_tokens,
            "prompt_tokens": usage.prompt_tokens,
            "output_tokens": usage.output_tokens,
            "requests": usage.requests,
            "truncated": usage.truncated,
            "validation_repair": validation_repair,
        }
        self._write(event)

    def record_feedback(
        self,
        tool: str,
        verdict: str,
        reason: str,
        *,
        profile_version: str,
    ) -> CanaryFeedbackReceipt:
        if not self.canary_active:
            return CanaryFeedbackReceipt(
                status="complete",
                feedback_count=self._feedback_count,
                target=CANARY_TARGET,
            )
        event = {
            "schema_version": 3,
            "event_type": "canary_feedback",
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool,
            "profile_version": profile_version,
            "source": "interactive",
            "verdict": verdict,
            "reason": reason,
        }
        self._write(event)
        self._feedback_count += 1
        return CanaryFeedbackReceipt(
            status="recorded",
            feedback_count=self._feedback_count,
            target=CANARY_TARGET,
        )

    def _count_existing_feedback(self) -> int:
        if self.path is None or not self.path.exists():
            return 0
        count = 0
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                count += event.get("event_type") == "canary_feedback"
        except OSError:
            return 0
        return count

    def _write(self, event: dict[str, object]) -> None:
        line = json.dumps(event, separators=(",", ":"))
        print(line, file=sys.stderr, flush=True)
        if self.path is not None:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.parent.chmod(0o700)
                with self.path.open("a", encoding="utf-8") as metrics:
                    metrics.write(line + "\n")
                self.path.chmod(0o600)
            except OSError:
                pass
