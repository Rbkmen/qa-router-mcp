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
                "schema_version": 4,
                "timestamp": timestamp,
                "tool": "test_cases",
                "outcome": "ok",
                "source": "interactive",
                "profile_version": "router-v7",
                "draft_id": "a" * 32,
            }
        ),
        json.dumps(
            {
                "schema_version": 4,
                "event_type": "canary_feedback",
                "timestamp": timestamp,
                "tool": "test_cases",
                "profile_version": "router-v7",
                "draft_id": "a" * 32,
                "source": "interactive",
                "verdict": "edited",
                "reason": "coverage",
            }
        ),
        json.dumps(
            {
                "schema_version": 4,
                "timestamp": timestamp,
                "tool": "translation",
                "outcome": "ok",
                "source": "interactive",
                "profile_version": "router-v7",
                "draft_id": "b" * 32,
            }
        ),
        json.dumps(
            {
                "schema_version": 4,
                "event_type": "canary_feedback",
                "timestamp": timestamp,
                "tool": "translation",
                "profile_version": "router-v7",
                "draft_id": "b" * 32,
                "source": "interactive",
                "verdict": "accepted",
                "reason": "none",
            }
        ),
    ]

    report = summarize_events(lines)

    assert report["events"] == 2
    assert report["outcomes"] == {"ok": 2}
    assert report["canary_feedback"] == {
        "target_per_profile": 50,
        "targets_by_tool": {
            "automation_skeleton": 10,
            "log_summary": 10,
            "rewrite": 3,
            "test_cases": 15,
            "text_summary": 10,
            "translation": 2,
        },
        "by_profile": {
            "router-v7": {
                "reviews": 2,
                "complete": False,
                "progress_by_tool": {
                    "automation_skeleton": 0,
                    "log_summary": 0,
                    "rewrite": 0,
                    "test_cases": 1,
                    "text_summary": 0,
                    "translation": 1,
                },
                "verdicts": {"accepted": 1, "edited": 1},
                "reasons": {"coverage": 1, "none": 1},
                "by_tool": {
                    "test_cases": {"edited": 1},
                    "translation": {"accepted": 1},
                },
            }
        },
    }


def test_canary_feedback_progress_is_lifetime_not_weekly():
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    report = summarize_events(
        [
            json.dumps(
                {
                    "schema_version": 4,
                    "timestamp": old_timestamp,
                    "tool": "test_cases",
                    "outcome": "ok",
                    "source": "interactive",
                    "profile_version": "router-v7",
                    "draft_id": "a" * 32,
                }
            ),
            json.dumps(
                {
                    "schema_version": 4,
                    "event_type": "canary_feedback",
                    "timestamp": old_timestamp,
                    "tool": "test_cases",
                    "profile_version": "router-v7",
                    "draft_id": "a" * 32,
                    "source": "interactive",
                    "verdict": "accepted",
                    "reason": "none",
                }
            ),
        ]
    )

    assert report["events"] == 0
    assert report["canary_feedback"]["by_profile"]["router-v7"]["reviews"] == 1


def test_canary_feedback_keeps_profile_versions_separate():
    timestamp = datetime.now(UTC).isoformat()
    lines = []
    for profile, draft_id, verdict, reason in (
        ("router-v7", "a" * 32, "accepted", "none"),
        ("router-v8", "b" * 32, "rejected", "factual"),
    ):
        lines.extend(
            [
                json.dumps(
                    {
                        "schema_version": 4,
                        "timestamp": timestamp,
                        "tool": "test_cases",
                        "outcome": "ok",
                        "source": "interactive",
                        "profile_version": profile,
                        "draft_id": draft_id,
                    }
                ),
                json.dumps(
                    {
                        "schema_version": 4,
                        "event_type": "canary_feedback",
                        "timestamp": timestamp,
                        "tool": "test_cases",
                        "profile_version": profile,
                        "draft_id": draft_id,
                        "source": "interactive",
                        "verdict": verdict,
                        "reason": reason,
                    }
                ),
            ]
        )

    profiles = summarize_events(lines)["canary_feedback"]["by_profile"]

    assert profiles["router-v7"]["verdicts"] == {"accepted": 1}
    assert profiles["router-v8"]["verdicts"] == {"rejected": 1}


def test_weekly_report_aggregates_qa_task_outcomes_separately():
    timestamp = datetime.now(UTC).isoformat()
    lines = [
        json.dumps(
            {
                "schema_version": 6,
                "event_type": "qa_task_outcome",
                "timestamp": timestamp,
                "task_type": "ordinary_review",
                "outcome": "completed",
                "codegraph_calls": 2,
                "source_mcp_calls": 7,
                "qwen_used": True,
                "sol_used": False,
                "findings_identified": 3,
                "findings_confirmed": 2,
                "findings_rejected": 1,
                "qwen_edits": 1,
                "repeated_source_reads": 0,
            }
        ),
        json.dumps(
            {
                "schema_version": 6,
                "event_type": "qa_task_outcome",
                "timestamp": timestamp,
                "task_type": "qa_planning",
                "outcome": "partial",
                "codegraph_calls": 0,
                "source_mcp_calls": 3,
                "qwen_used": False,
                "sol_used": True,
                "findings_identified": 1,
                "findings_confirmed": 1,
                "findings_rejected": 0,
                "qwen_edits": 0,
                "repeated_source_reads": 1,
            }
        ),
    ]

    report = summarize_events(lines)

    assert report["events"] == 0
    assert report["qa_tasks"] == {
        "events": 2,
        "outcomes": {"completed": 1, "partial": 1},
        "by_task_type": {"ordinary_review": 1, "qa_planning": 1},
        "codegraph_calls": 2,
        "source_mcp_calls": 10,
        "qwen_tasks": 1,
        "sol_tasks": 1,
        "findings_identified": 4,
        "findings_confirmed": 3,
        "findings_rejected": 1,
        "qwen_edits": 1,
        "repeated_source_reads": 1,
    }


def test_weekly_report_ignores_invalid_qa_task_outcomes():
    timestamp = datetime.now(UTC).isoformat()
    invalid = {
        "schema_version": 6,
        "event_type": "qa_task_outcome",
        "timestamp": timestamp,
        "task_type": "ordinary_review",
        "outcome": "completed",
        "codegraph_calls": 1,
        "source_mcp_calls": 0,
        "qwen_used": False,
        "sol_used": False,
        "findings_identified": 0,
        "findings_confirmed": 1,
        "findings_rejected": 0,
        "qwen_edits": 0,
        "repeated_source_reads": 0,
    }

    report = summarize_events([json.dumps(invalid)])

    assert report["events"] == 0
    assert report["qa_tasks"]["events"] == 0
