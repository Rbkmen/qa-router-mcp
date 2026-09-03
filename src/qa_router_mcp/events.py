import json
import sys
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from fcntl import LOCK_EX, LOCK_UN, flock
from pathlib import Path
from re import fullmatch
from typing import IO, Protocol

from qa_router_mcp.contracts import CanaryFeedbackReceipt, GenerationStats

CANARY_TOOL_TARGETS = {
    "test_cases": 15,
    "log_summary": 10,
    "automation_skeleton": 10,
    "text_summary": 10,
    "rewrite": 3,
    "translation": 2,
}
CANARY_TARGET = sum(CANARY_TOOL_TARGETS.values())
CANARY_VERDICTS = {"accepted", "edited", "rejected"}
CANARY_REASONS = {"none", "factual", "coverage", "format", "too_verbose", "other"}


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
        draft_id: str | None = None,
    ) -> str | None: ...

    def canary_active(self, tool: str) -> bool: ...

    def record_feedback(
        self,
        draft_id: str,
        verdict: str,
        reason: str,
    ) -> CanaryFeedbackReceipt: ...


class JsonEventSink:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path

    def canary_active(self, tool: str) -> bool:
        if self.path is None or tool not in CANARY_TOOL_TARGETS:
            return False
        try:
            with self._locked_events() as (_, events):
                issued = Counter(
                    str(draft["tool"]) for draft in _issued_canary_drafts(events).values()
                )
                return issued[tool] < CANARY_TOOL_TARGETS[tool]
        except OSError:
            return False

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
        draft_id: str | None = None,
    ) -> str | None:
        usage = stats or GenerationStats()
        event: dict[str, object] = {
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
        if draft_id is None:
            self._write(event)
            return None
        return self._write_canary_candidate(event, draft_id)

    def record_feedback(
        self,
        draft_id: str,
        verdict: str,
        reason: str,
    ) -> CanaryFeedbackReceipt:
        if self.path is None:
            return self._receipt("unavailable", 0)
        if not _valid_feedback_values(verdict, reason):
            return self._receipt("invalid", 0)
        try:
            with self._locked_events() as (metrics, events):
                feedback = validated_canary_feedback(events)
                issued = _issued_canary_drafts(events)
                feedback_ids = {str(event["draft_id"]) for event in feedback}
                if draft_id in feedback_ids:
                    return self._receipt("duplicate", len(feedback))
                draft = issued.get(draft_id)
                if draft is None:
                    return self._receipt("not_found", len(feedback))
                tool = str(draft["tool"])
                progress = Counter(str(event["tool"]) for event in feedback)
                if progress[tool] >= CANARY_TOOL_TARGETS[tool]:
                    return self._receipt("complete", len(feedback))
                event = {
                    "schema_version": 4,
                    "event_type": "canary_feedback",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "tool": tool,
                    "draft_id": draft_id,
                    "profile_version": draft["profile_version"],
                    "source": "interactive",
                    "verdict": verdict,
                    "reason": reason,
                }
                self._append_locked(metrics, event)
                print(_serialize(event), file=sys.stderr, flush=True)
                return self._receipt("recorded", len(feedback) + 1)
        except OSError:
            return self._receipt("unavailable", 0)

    @staticmethod
    def _receipt(status: str, feedback_count: int) -> CanaryFeedbackReceipt:
        return CanaryFeedbackReceipt(
            status=status,
            feedback_count=feedback_count,
            target=CANARY_TARGET,
        )

    @contextmanager
    def _locked_events(self) -> Iterator[tuple[IO[str], list[dict[str, object]]]]:
        if self.path is None:
            raise OSError("metrics path is unavailable")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        with self.path.open("a+", encoding="utf-8") as metrics:
            flock(metrics.fileno(), LOCK_EX)
            try:
                metrics.seek(0)
                events = _parse_events(metrics)
                yield metrics, events
                self.path.chmod(0o600)
            finally:
                flock(metrics.fileno(), LOCK_UN)

    @staticmethod
    def _append_locked(metrics: IO[str], event: dict[str, object]) -> None:
        metrics.seek(0, 2)
        metrics.write(_serialize(event) + "\n")
        metrics.flush()

    def _write(self, event: dict[str, object]) -> bool:
        line = _serialize(event)
        print(line, file=sys.stderr, flush=True)
        if self.path is None:
            return True
        try:
            with self._locked_events() as (metrics, _):
                self._append_locked(metrics, event)
            return True
        except OSError:
            return False

    def _write_canary_candidate(
        self,
        event: dict[str, object],
        draft_id: str,
    ) -> str | None:
        if self.path is None:
            return None
        try:
            with self._locked_events() as (metrics, events):
                tool = str(event["tool"])
                issued = Counter(
                    str(draft["tool"]) for draft in _issued_canary_drafts(events).values()
                )
                if tool not in CANARY_TOOL_TARGETS or issued[tool] >= CANARY_TOOL_TARGETS[tool]:
                    self._append_locked(metrics, event)
                    print(_serialize(event), file=sys.stderr, flush=True)
                    return None
                event["schema_version"] = 4
                event["draft_id"] = draft_id
                self._append_locked(metrics, event)
                print(_serialize(event), file=sys.stderr, flush=True)
                return draft_id
        except OSError:
            return None


def validated_canary_feedback(events: list[dict[str, object]]) -> list[dict[str, object]]:
    issued = _issued_canary_drafts(events)
    seen: set[str] = set()
    valid: list[dict[str, object]] = []
    for event in events:
        if (
            event.get("schema_version") != 4
            or event.get("event_type") != "canary_feedback"
            or event.get("source") != "interactive"
        ):
            continue
        draft_id = event.get("draft_id")
        draft = issued.get(draft_id) if isinstance(draft_id, str) else None
        if draft is None or draft_id in seen:
            continue
        if event.get("tool") != draft.get("tool"):
            continue
        if event.get("profile_version") != draft.get("profile_version"):
            continue
        verdict = event.get("verdict")
        reason = event.get("reason")
        if not isinstance(verdict, str) or not isinstance(reason, str):
            continue
        if not _valid_feedback_values(verdict, reason):
            continue
        seen.add(draft_id)
        valid.append(event)
    return valid


def _issued_canary_drafts(
    events: list[dict[str, object]],
) -> dict[str, dict[str, object]]:
    issued: dict[str, dict[str, object]] = {}
    for event in events:
        draft_id = event.get("draft_id")
        tool = event.get("tool")
        if (
            isinstance(draft_id, str)
            and fullmatch(r"[0-9a-f]{32}", draft_id)
            and isinstance(tool, str)
            and tool in CANARY_TOOL_TARGETS
            and event.get("outcome") == "ok"
            and event.get("source") == "interactive"
            and isinstance(event.get("profile_version"), str)
        ):
            issued[draft_id] = event
    return issued


def _parse_events(metrics: IO[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in metrics:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _serialize(event: dict[str, object]) -> str:
    return json.dumps(event, separators=(",", ":"))


def _valid_feedback_values(verdict: str, reason: str) -> bool:
    return (
        verdict in CANARY_VERDICTS
        and reason in CANARY_REASONS
        and ((verdict == "accepted") == (reason == "none"))
    )
