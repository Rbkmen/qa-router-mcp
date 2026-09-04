import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from os import environ
from pathlib import Path

from qa_router_mcp.events import (
    CANARY_TARGET,
    CANARY_TOOL_TARGETS,
    QA_TASK_TOKEN_COUNTERS,
    valid_qa_task_metrics,
    validated_canary_feedback,
)


def summarize_events(lines: Iterable[str], days: int = 7) -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    outcomes: Counter[str] = Counter()
    tools: dict[str, Counter[str]] = defaultdict(Counter)
    sources: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    models: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    profiles: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    feedback_by_profile: dict[str, list[dict[str, object]]] = defaultdict(list)
    totals = Counter()
    durations: list[float] = []
    phase_durations: dict[str, list[float]] = defaultdict(list)
    cold_starts: Counter[str] = Counter()
    quality_statuses: Counter[str] = Counter()
    shadow_requested = 0
    shadow_eligible = 0
    qa_task_outcomes: Counter[str] = Counter()
    qa_task_types: Counter[str] = Counter()
    qa_task_totals = Counter()

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
        feedback_by_profile[str(event["profile_version"])].append(event)

    for event in events:
        if event.get("event_type") == "canary_feedback":
            continue
        try:
            timestamp = datetime.fromisoformat(str(event["timestamp"]))
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp < cutoff:
            continue
        if event.get("event_type") == "qa_task_outcome":
            if event.get("schema_version") not in {6, 7} or not valid_qa_task_metrics(event):
                continue
            qa_task_outcomes[str(event.get("outcome", "unknown"))] += 1
            qa_task_types[str(event.get("task_type", "unknown"))] += 1
            qa_task_totals["events"] += 1
            qa_task_totals["qwen_tasks"] += event.get("qwen_used") is True
            qa_task_totals["sol_tasks"] += event.get("sol_used") is True
            qa_task_totals["codegraph_tasks"] += event.get("codegraph_calls", 0) > 0
            qa_task_totals["complete_token_measurement_tasks"] += QA_TASK_TOKEN_COUNTERS <= event.keys()
            for field in (
                "codegraph_calls",
                "source_mcp_calls",
                "findings_identified",
                "findings_confirmed",
                "findings_rejected",
                "qwen_edits",
                "repeated_source_reads",
                "codegraph_response_tokens",
                "source_mcp_response_tokens",
                "avoided_source_read_tokens",
            ):
                value = event.get(field, 0)
                if type(value) is int and value >= 0:
                    qa_task_totals[field] += value
            continue
        tool = str(event.get("tool", "unknown"))
        outcome = str(event.get("outcome", "unknown"))
        has_metadata = event.get("schema_version") in {2, 4, 7}
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
        if event.get("schema_version") == 7:
            for phase in ("model_load", "tokenization", "generation", "validation", "repair"):
                value = event.get(f"{phase}_ms")
                if isinstance(value, (int, float)) and value >= 0:
                    phase_durations[phase].append(float(value))
            cold = event.get("cold_start_likely")
            if type(cold) is bool:
                cold_starts[str(cold).lower()] += 1
            quality = event.get("quality_status")
            if quality in {"active", "canary", "paused"}:
                quality_statuses[str(quality)] += 1
            if outcome == "ok" and source == "interactive":
                shadow_eligible += 1
                shadow_requested += event.get("shadow_evaluation_required") is True

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
        "phase_latency_ms": {
            f"{phase}_{percentile}": _percentile(values, fraction)
            for phase, values in phase_durations.items()
            for percentile, fraction in (("p50", 0.50), ("p95", 0.95))
        },
        "cold_start_likely": dict(sorted(cold_starts.items())),
        "shadow_evaluations": {
            "requested": shadow_requested,
            "rate": round(shadow_requested / shadow_eligible, 3) if shadow_eligible else None,
        },
        "quality_statuses": dict(sorted(quality_statuses.items())),
        "by_tool": {
            tool: dict(sorted(tool_outcomes.items()))
            for tool, tool_outcomes in sorted(tools.items())
        },
        "by_source": _dimension_summary(sources),
        "by_model": _dimension_summary(models),
        "by_profile": _dimension_summary(profiles),
        "canary_feedback": {
            "target_per_profile": CANARY_TARGET,
            "targets_by_tool": dict(sorted(CANARY_TOOL_TARGETS.items())),
            "by_profile": {
                profile: _canary_profile_summary(entries)
                for profile, entries in sorted(feedback_by_profile.items())
            },
        },
        "qa_tasks": {
            "events": qa_task_totals["events"],
            "outcomes": dict(sorted(qa_task_outcomes.items())),
            "by_task_type": dict(sorted(qa_task_types.items())),
            "codegraph_calls": qa_task_totals["codegraph_calls"],
            "source_mcp_calls": qa_task_totals["source_mcp_calls"],
            "qwen_tasks": qa_task_totals["qwen_tasks"],
            "sol_tasks": qa_task_totals["sol_tasks"],
            "findings_identified": qa_task_totals["findings_identified"],
            "findings_confirmed": qa_task_totals["findings_confirmed"],
            "findings_rejected": qa_task_totals["findings_rejected"],
            "qwen_edits": qa_task_totals["qwen_edits"],
            "repeated_source_reads": qa_task_totals["repeated_source_reads"],
            "codegraph": {
                "tasks": qa_task_totals["codegraph_tasks"],
                "calls": qa_task_totals["codegraph_calls"],
                "response_tokens": qa_task_totals["codegraph_response_tokens"],
                "avoided_source_read_tokens": qa_task_totals["avoided_source_read_tokens"],
                "estimated_source_token_savings_pct": _savings_percent(
                    qa_task_totals["avoided_source_read_tokens"],
                    qa_task_totals["source_mcp_response_tokens"],
                ),
            },
            "source_mcp_response_tokens": qa_task_totals["source_mcp_response_tokens"],
            "complete_token_measurement_tasks": qa_task_totals["complete_token_measurement_tasks"],
        },
    }


def _canary_profile_summary(events: list[dict[str, object]]) -> dict[str, object]:
    verdicts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    tools: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        tool = str(event["tool"])
        verdict = str(event["verdict"])
        verdicts[verdict] += 1
        reasons[str(event["reason"])] += 1
        tools[tool][verdict] += 1
    progress = {tool: sum(tools.get(tool, {}).values()) for tool in CANARY_TOOL_TARGETS}
    return {
        "reviews": verdicts.total(),
        "complete": all(progress[tool] >= target for tool, target in CANARY_TOOL_TARGETS.items()),
        "progress_by_tool": dict(sorted(progress.items())),
        "verdicts": dict(sorted(verdicts.items())),
        "reasons": dict(sorted(reasons.items())),
        "by_tool": {
            tool: dict(sorted(tool_verdicts.items()))
            for tool, tool_verdicts in sorted(tools.items())
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


def _savings_percent(avoided_tokens: int, source_tokens: int) -> float | None:
    total = avoided_tokens + source_tokens
    return round(avoided_tokens / total * 100, 1) if total else None


def main() -> None:
    data_dir = Path(environ.get("QA_ROUTER_DATA_DIR", str(Path.home() / ".qa-router")))
    path = data_dir / "metrics.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    print(json.dumps(summarize_events(lines), ensure_ascii=False, indent=2))
