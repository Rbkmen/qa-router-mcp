from datetime import UTC, datetime

from qa_router_mcp.quality import assess_quality, is_shadow_sample


def _feedback(verdict: str, reason: str) -> dict[str, object]:
    return {
        "schema_version": 4,
        "event_type": "canary_feedback",
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": "test_cases",
        "draft_id": "a" * 32,
        "profile_version": "router-v10",
        "source": "interactive",
        "verdict": verdict,
        "reason": reason,
    }


def test_quality_gate_pauses_after_twenty_percent_serious_reviews():
    events = [_feedback("accepted", "none") for _ in range(8)]
    events += [_feedback("edited", "coverage"), _feedback("rejected", "factual")]

    gate = assess_quality("test_cases", events)

    assert gate.status == "paused"
    assert gate.reviews == 10
    assert gate.acceptable_rate == 0.8
    assert gate.serious_rate == 0.2


def test_quality_gate_activates_after_eighty_percent_acceptable_reviews():
    events = [_feedback("accepted", "none") for _ in range(8)]
    events += [_feedback("edited", "format"), _feedback("rejected", "other")]

    gate = assess_quality("test_cases", events)

    assert gate.status == "active"
    assert gate.acceptable_rate == 0.9
    assert gate.serious_rate == 0.0


def test_quality_gate_uses_conservative_tool_defaults_before_ten_reviews():
    assert assess_quality("test_cases", []).status == "canary"
    assert assess_quality("log_summary", []).status == "canary"
    assert assess_quality("translation", []).status == "active"
    assert assess_quality("rewrite", []).status == "active"
    assert assess_quality("text_summary", []).status == "active"


def test_shadow_sample_is_deterministic_and_ten_percent_by_bucket():
    sampled = [is_shadow_sample(f"{index:032x}") for index in range(100)]

    assert sum(sampled) == 10
    assert sampled == [is_shadow_sample(f"{index:032x}") for index in range(100)]


def test_quality_gate_uses_only_latest_twenty_reviews():
    old_serious = [_feedback("edited", "coverage") for _ in range(10)]
    recent_accepted = [_feedback("accepted", "none") for _ in range(20)]

    gate = assess_quality("test_cases", old_serious + recent_accepted)

    assert gate.status == "active"
    assert gate.reviews == 20
    assert gate.serious_rate == 0.0
