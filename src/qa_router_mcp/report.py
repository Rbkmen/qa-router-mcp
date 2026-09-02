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
        outcomes[outcome] += 1
        tools[tool][outcome] += 1
        totals["events"] += 1
        for field in ("prompt_tokens", "output_tokens", "requests"):
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
    }


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
