import pytest
from pydantic import ValidationError

from qa_router_mcp.contracts import CoverageItem, DraftEnvelope, GenerationStats


def test_successful_qa_shaped_draft_keeps_unverified_items():
    result = DraftEnvelope(draft="Case A", unverified=["Expected result"])

    assert result.status == "ok"
    assert result.unverified == ["Expected result"]


def test_successful_routine_draft_may_have_no_unverified_items():
    result = DraftEnvelope(draft="Translated text", unverified=[])

    assert result.status == "ok"
    assert result.unverified == []


def test_successful_draft_requires_content():
    with pytest.raises(ValidationError):
        DraftEnvelope(draft="", unverified=[])


def test_successful_draft_discards_model_generated_reason():
    result = DraftEnvelope(
        draft="Case A",
        unverified=["Expected result"],
        reason="generated task content must not reach operational logs",
    )

    assert result.reason is None


def test_generation_stats_are_runtime_only():
    result = DraftEnvelope(draft="Case A", unverified=["Review"])
    result.set_generation_stats(GenerationStats(prompt_tokens=20, output_tokens=10, requests=1))

    assert result.generation_stats.output_tokens == 10
    assert "generation_stats" not in result.model_dump()
    assert "generation_stats" not in DraftEnvelope.model_json_schema()["properties"]


@pytest.mark.parametrize("field", ["purpose", "source", "state", "expected_invariant"])
def test_coverage_item_rejects_whitespace_only_fields(field):
    values = {
        "coverage_id": "COV-CHECKOUT",
        "purpose": "Purpose",
        "source": "Source",
        "state": "State",
        "expected_invariant": "Expected",
    }
    values[field] = " \n\t"

    with pytest.raises(ValidationError):
        CoverageItem(**values)
