import pytest
from pydantic import ValidationError

from qa_router_mcp.contracts import (
    DraftEnvelope,
    LearningEnvelope,
    LearningProposal,
    ProposalStatus,
)


def test_successful_draft_is_always_unverified():
    result = DraftEnvelope(draft="Case A", unverified=["Expected result"])

    assert result.status == "ok"
    assert result.unverified == ["Expected result"]


def test_successful_draft_requires_unverified_items():
    with pytest.raises(ValidationError):
        DraftEnvelope(draft="Case A", unverified=[])


def test_successful_draft_discards_model_generated_reason():
    result = DraftEnvelope(
        draft="Case A",
        unverified=["Expected result"],
        reason="generated task content must not reach operational logs",
    )

    assert result.reason is None


def test_learning_proposal_starts_pending():
    proposal = LearningProposal(id="lp_123", text="Use Given/When/Then headings")

    assert proposal.status is ProposalStatus.PENDING


def test_learning_fallback_requires_reason():
    result = LearningEnvelope(status="fallback", reason="hermes_timeout")

    assert result.proposal is None
