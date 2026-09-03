import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from os import environ
from pathlib import Path

from qa_router_mcp.events import (
    CANARY_TARGET,
    CANARY_TOOL_TARGETS,
    validated_canary_feedback,
)


def summarize_events(lines: Iterable[str], days: int = 7) -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    outcomes: Counter[str] = Counter()
    tools: dict[str, Counter[str]] = defaultdict(Counter)
    sources: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    models: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    profiles: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    feedback_verdicts: Counter[str] = Counter()
    feedback_reasons: Counter[str] = Counter()
    feedback_tools: dict[str, Counter[str]] = defaultdict(Counter)
    totals = Counter()
    durations: list[float] = []

    events: list[dict[str, object]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)

    feedback = validated_canary_feedback(events)
    for event in feedback:
        tool = str(event["tool"])
        verdict = str(event.get("verdict", "unknown"))
        reason = str(event.get("reason", "unknown"))
        feedback_verdicts[verdict] += 1
        feedback_reasons[reason] += 1
        feedback_tools[tool][verdict] += 1

    for event in events:
        if event.get("event_type") == "canary_feedback":
            continue
        try:
            timestamp = datetime.fromisoformat(str(event["timestamp"]))
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp < cutoff:
            continue
        tool = str(event.get("tool", "unknown"))
        outcome = str(event.get("outcome", "unknown"))
        has_metadata = event.get("schema_version") in {2, 4}
        source = str(event.get("source", "legacy")) if has_metadata else "legacy"
        model = str(event.get("model", "unknown")) if has_metadata else "unknown"
        profile = str(event.get("profile_version", "legacy")) if has_metadata else "legacy"
        outcomes[outcome] += 1
        tools[tool][outcome] += 1
        sources[source].append((outcome, event))
        models[model].append((outcome, event))
        profiles[profile].append((outcome, event))
        totals["events"] += 1
        for field in (
            "estimated_prompt_tokens",
            "prompt_tokens",
            "output_tokens",
            "requests",
        ):
            value = event.get(field, 0)
            if isinstance(value, int) and value >= 0:
                totals[field] += value
        totals["validation_repairs"] += bool(event.get("validation_repair"))
        totals["truncations"] += bool(event.get("truncated"))
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)) and duration >= 0:
            durations.append(float(duration))

    feedback_progress = {
        tool: sum(feedback_tools.get(tool, {}).values()) for tool in CANARY_TOOL_TARGETS
    }
    return {
        "period_days": days,
        "events": totals["events"],
        "outcomes": dict(sorted(outcomes.items())),
        "prompt_tokens": totals["prompt_tokens"],
        "estimated_prompt_tokens": totals["estimated_prompt_tokens"],
        "output_tokens": totals["output_tokens"],
        "requests": totals["requests"],
        "validation_repairs": totals["validation_repairs"],
        "truncations": totals["truncations"],
        "duration_ms_p50": _percentile(durations, 0.50),
        "duration_ms_p95": _percentile(durations, 0.95),
        "by_tool": {
            tool: dict(sorted(tool_outcomes.items()))
            for tool, tool_outcomes in sorted(tools.items())
        },
        "by_source": _dimension_summary(sources),
        "by_model": _dimension_summary(models),
        "by_profile": _dimension_summary(profiles),
        "canary_feedback": {
            "target": CANARY_TARGET,
            "reviews": feedback_verdicts.total(),
            "complete": all(
                feedback_progress[tool] >= target for tool, target in CANARY_TOOL_TARGETS.items()
            ),
            "targets_by_tool": dict(sorted(CANARY_TOOL_TARGETS.items())),
            "progress_by_tool": dict(sorted(feedback_progress.items())),
            "verdicts": dict(sorted(feedback_verdicts.items())),
            "reasons": dict(sorted(feedback_reasons.items())),
            "by_tool": {
                tool: dict(sorted(verdicts.items()))
                for tool, verdicts in sorted(feedback_tools.items())
            },
        },
    }


def _dimension_summary(
    values: dict[str, list[tuple[str, dict[str, object]]]],
) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for key, entries in sorted(values.items()):
        outcomes: Counter[str] = Counter()
        totals = Counter()
        durations: list[float] = []
        for outcome, event in entries:
            outcomes[outcome] += 1
            for field in (
                "estimated_prompt_tokens",
                "prompt_tokens",
                "output_tokens",
                "requests",
            ):
                value = event.get(field, 0)
                if isinstance(value, int) and value >= 0:
                    totals[field] += value
            duration = event.get("duration_ms")
            if isinstance(duration, (int, float)) and duration >= 0:
                durations.append(float(duration))
        summary[key] = {
            "events": len(entries),
            "outcomes": dict(sorted(outcomes.items())),
            "estimated_prompt_tokens": totals["estimated_prompt_tokens"],
            "prompt_tokens": totals["prompt_tokens"],
            "output_tokens": totals["output_tokens"],
            "requests": totals["requests"],
            "duration_ms_p50": _percentile(durations, 0.50),
            "duration_ms_p95": _percentile(durations, 0.95),
        }
    return summary


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def main() -> None:
    data_dir = Path(environ.get("QA_ROUTER_DATA_DIR", "/Users/andreiviarshko/.qa-router"))
    path = data_dir / "metrics.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    print(json.dumps(summarize_events(lines), ensure_ascii=False, indent=2))
