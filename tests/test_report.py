import json
from datetime import UTC, datetime

from qa_router_mcp.report import summarize_events


def test_weekly_report_aggregates_metadata_only():
    timestamp = datetime.now(UTC).isoformat()
    lines = [
        json.dumps(
            {
                "timestamp": timestamp,
                "tool": "test_cases",
                "outcome": "ok",
                "prompt_tokens": 100,
                "output_tokens": 50,
                "requests": 1,
                "duration_ms": 10.0,
                "validation_repair": False,
                "truncated": False,
            }
        ),
        json.dumps(
            {
                "timestamp": timestamp,
                "tool": "test_cases",
                "outcome": "fallback",
                "prompt_tokens": 120,
                "output_tokens": 60,
                "requests": 2,
                "duration_ms": 30.0,
                "validation_repair": True,
                "truncated": False,
            }
        ),
        "invalid line",
    ]

    report = summarize_events(lines)

    assert report["events"] == 2
    assert report["outcomes"] == {"fallback": 1, "ok": 1}
    assert report["prompt_tokens"] == 220
    assert report["output_tokens"] == 110
    assert report["validation_repairs"] == 1
    assert report["duration_ms_p50"] == 10.0
    assert report["duration_ms_p95"] == 30.0
    assert report["by_tool"] == {"test_cases": {"fallback": 1, "ok": 1}}
