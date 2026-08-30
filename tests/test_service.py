import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.events import JsonEventSink
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


class DraftFake:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return self.result


class LearningFake:
    def __init__(self):
        self.texts = []

    async def apply(self, text):
        self.texts.append(text)
        return "stored"


@pytest.mark.asyncio
async def test_draft_sanitizes_and_queues_safe_learning(tmp_path):
    drafting = DraftFake(
        DraftEnvelope(
            draft="Case",
            unverified=["Expected result"],
            learning_proposal="Use concise case titles",
        )
    )
    service = RouterService(
        Settings(data_dir=tmp_path), drafting, LearningFake(), ProposalStore(tmp_path)
    )

    result = await service.draft(
        DraftKind.TEST_CASES,
        "ABC-123 at https://stage.test",
    )

    assert result.status == "ok"
    assert "ABC-123" not in drafting.prompts[0]
    assert "[ISSUE]" in drafting.prompts[0]
    assert len(service.list_proposals()) == 1


@pytest.mark.asyncio
async def test_policy_failure_returns_refusal_without_backend_call(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    service = RouterService(
        Settings(data_dir=tmp_path), drafting, LearningFake(), ProposalStore(tmp_path)
    )

    result = await service.draft(DraftKind.TEST_CASES, "password=secret")

    assert result.status == "refused"
    assert result.reason == "secret_detected"
    assert drafting.prompts == []


@pytest.mark.asyncio
async def test_combined_packet_limit_is_enforced_before_backend(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    settings = Settings(data_dir=tmp_path, max_input_chars=10)
    service = RouterService(settings, drafting, LearningFake(), ProposalStore(tmp_path))

    result = await service.draft(DraftKind.AUTOMATION_SKELETON, "123456", "78901")

    assert result.status == "refused"
    assert result.reason == "input_too_large"
    assert drafting.prompts == []


@pytest.mark.asyncio
async def test_approval_sends_only_stored_validated_text(tmp_path):
    learning = LearningFake()
    store = ProposalStore(tmp_path)
    proposal = store.add("Use concise case titles")
    service = RouterService(Settings(data_dir=tmp_path), DraftFake(None), learning, store)

    approved = await service.approve_proposal(proposal.id)

    assert approved.status == "approved"
    assert approved.proposal is not None
    assert approved.proposal.id == proposal.id
    assert learning.texts == ["Use concise case titles"]


@pytest.mark.asyncio
async def test_hermes_failure_keeps_proposal_pending(tmp_path):
    class FailingLearning:
        async def apply(self, text):
            raise BackendError("hermes_timeout")

    store = ProposalStore(tmp_path)
    proposal = store.add("Use concise case titles")
    service = RouterService(
        Settings(data_dir=tmp_path), DraftFake(None), FailingLearning(), store
    )

    result = await service.approve_proposal(proposal.id)

    assert result.status == "fallback"
    assert result.reason == "hermes_timeout"
    assert store.get_pending(proposal.id).status == "pending"


def test_event_sink_never_logs_content(capsys):
    JsonEventSink().emit("draft_test_cases", "refused", 1.25, "secret_detected")

    event = capsys.readouterr().err
    assert "draft_test_cases" in event
    assert "secret_detected" in event
    assert "password=secret" not in event
