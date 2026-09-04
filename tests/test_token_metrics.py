import json
from datetime import UTC, datetime

from qa_router_mcp.events import valid_qa_task_metrics
from qa_router_mcp.report import summarize_events


def test_report_aggregates_codegraph_token_estimate():
    event = {
        "schema_version": 7,
        "event_type": "qa_task_outcome",
        "timestamp": datetime.now(UTC).isoformat(),
        "task_type": "ordinary_review",
        "outcome": "completed",
        "codegraph_calls": 2,
        "source_mcp_calls": 5,
        "qwen_used": False,
        "sol_used": False,
        "findings_identified": 0,
        "findings_confirmed": 0,
        "findings_rejected": 0,
        "qwen_edits": 0,
        "repeated_source_reads": 0,
        "codegraph_response_tokens": 600,
        "source_mcp_response_tokens": 1800,
        "avoided_source_read_tokens": 200,
    }

    report = summarize_events([json.dumps(event)])

    assert report["qa_tasks"]["codegraph"] == {
        "tasks": 1,
        "calls": 2,
        "response_tokens": 600,
        "avoided_source_read_tokens": 200,
        "estimated_source_token_savings_pct": 10.0,
    }
    assert report["qa_tasks"]["source_mcp_response_tokens"] == 1800
    assert report["qa_tasks"]["complete_token_measurement_tasks"] == 1


def test_codegraph_token_metrics_require_codegraph_calls():
    event = {
        "task_type": "ordinary_review",
        "outcome": "completed",
        "codegraph_calls": 0,
        "source_mcp_calls": 0,
        "qwen_used": False,
        "sol_used": False,
        "findings_identified": 0,
        "findings_confirmed": 0,
        "findings_rejected": 0,
        "qwen_edits": 0,
        "repeated_source_reads": 0,
        "codegraph_response_tokens": 600,
        "avoided_source_read_tokens": 200,
    }

    assert valid_qa_task_metrics(event) is False


def test_source_token_metrics_require_source_calls():
    event = {
        "task_type": "ordinary_review",
        "outcome": "completed",
        "codegraph_calls": 1,
        "source_mcp_calls": 0,
        "qwen_used": False,
        "sol_used": False,
        "findings_identified": 0,
        "findings_confirmed": 0,
        "findings_rejected": 0,
        "qwen_edits": 0,
        "repeated_source_reads": 0,
        "source_mcp_response_tokens": 200,
    }

    assert valid_qa_task_metrics(event) is False
