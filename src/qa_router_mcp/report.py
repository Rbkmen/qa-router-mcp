import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from os import environ
from pathlib import Path


def summarize_events(lines: Iterable[str], days: int = 7) -> dict[str, object]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    outcomes: Counter[str] = Counter()
    tools: dict[str, Counter[str]] = defaultdict(Counter)
    sources: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    models: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    profiles: dict[str, list[tuple[str, dict[str, object]]]] = defaultdict(list)
    totals = Counter()
    durations: list[float] = []

    for line in lines:
        try:
            event = json.loads(line)
            timestamp = datetime.fromisoformat(event["timestamp"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if timestamp < cutoff:
            continue

        tool = str(event.get("tool", "unknown"))
        outcome = str(event.get("outcome", "unknown"))
        is_v2 = event.get("schema_version") == 2
        source = str(event.get("source", "legacy")) if is_v2 else "legacy"
        model = str(event.get("model", "unknown")) if is_v2 else "unknown"
        profile = str(event.get("profile_version", "legacy")) if is_v2 else "legacy"
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
