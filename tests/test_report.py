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
                "schema_version": 2,
                "timestamp": timestamp,
                "tool": "test_cases",
                "outcome": "fallback",
                "model": "qwen/qwen3.5-9b",
                "profile_version": "router-v2",
                "source": "benchmark",
                "estimated_prompt_tokens": 80,
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
    assert report["estimated_prompt_tokens"] == 80
    assert report["output_tokens"] == 110
    assert report["validation_repairs"] == 1
    assert report["duration_ms_p50"] == 10.0
    assert report["duration_ms_p95"] == 30.0
    assert report["by_tool"] == {"test_cases": {"fallback": 1, "ok": 1}}
    assert report["by_source"] == {
        "benchmark": {
            "events": 1,
            "outcomes": {"fallback": 1},
            "estimated_prompt_tokens": 80,
            "prompt_tokens": 120,
            "output_tokens": 60,
            "requests": 2,
            "duration_ms_p50": 30.0,
            "duration_ms_p95": 30.0,
        },
        "legacy": {
            "events": 1,
            "outcomes": {"ok": 1},
            "estimated_prompt_tokens": 0,
            "prompt_tokens": 100,
            "output_tokens": 50,
            "requests": 1,
            "duration_ms_p50": 10.0,
            "duration_ms_p95": 10.0,
        },
    }
    assert report["by_model"]["qwen/qwen3.5-9b"] == report["by_source"]["benchmark"]
    assert report["by_model"]["unknown"] == report["by_source"]["legacy"]
    assert report["by_profile"]["router-v2"] == report["by_source"]["benchmark"]
    assert report["by_profile"]["legacy"] == report["by_source"]["legacy"]


def test_weekly_report_separates_canary_feedback_from_generation_events():
    timestamp = datetime.now(UTC).isoformat()
    lines = [
        json.dumps(
            {
                "schema_version": 2,
                "timestamp": timestamp,
                "tool": "test_cases",
                "outcome": "ok",
                "source": "interactive",
            }
        ),
        json.dumps(
            {
                "schema_version": 3,
                "event_type": "canary_feedback",
                "timestamp": timestamp,
                "tool": "test_cases",
                "verdict": "edited",
                "reason": "coverage",
            }
        ),
        json.dumps(
            {
                "schema_version": 3,
                "event_type": "canary_feedback",
                "timestamp": timestamp,
                "tool": "translation",
                "verdict": "accepted",
                "reason": "none",
            }
        ),
    ]

    report = summarize_events(lines)

    assert report["events"] == 1
    assert report["outcomes"] == {"ok": 1}
    assert report["canary_feedback"] == {
        "target": 50,
        "reviews": 2,
        "complete": False,
        "verdicts": {"accepted": 1, "edited": 1},
        "reasons": {"coverage": 1, "none": 1},
        "by_tool": {
            "test_cases": {"edited": 1},
            "translation": {"accepted": 1},
        },
    }


def test_canary_feedback_progress_is_lifetime_not_weekly():
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    report = summarize_events(
        [
            json.dumps(
                {
                    "schema_version": 3,
                    "event_type": "canary_feedback",
                    "timestamp": old_timestamp,
                    "tool": "test_cases",
                    "verdict": "accepted",
                    "reason": "none",
                }
            )
        ]
    )

    assert report["events"] == 0
    assert report["canary_feedback"]["reviews"] == 1
