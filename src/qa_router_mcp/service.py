from time import monotonic

from qa_router_mcp.backends import BackendError, DraftBackend, LearningBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import (
    DraftEnvelope,
    DraftKind,
    LearningEnvelope,
    LearningProposal,
)
from qa_router_mcp.events import EventSink, JsonEventSink
from qa_router_mcp.policy import PolicyError, assert_allowed_request, sanitize_transient
from qa_router_mcp.prompts import build_prompt
from qa_router_mcp.store import ProposalStore

QA_DRAFT_KINDS = frozenset(
    {
        DraftKind.TEST_CASES,
        DraftKind.LOG_SUMMARY,
        DraftKind.AUTOMATION_SKELETON,
    }
)


class RouterService:
    def __init__(
        self,
        settings: Settings,
        drafting: DraftBackend,
        learning: LearningBackend,
        store: ProposalStore,
        events: EventSink | None = None,
    ) -> None:
        self.settings = settings
        self.drafting = drafting
        self.learning = learning
        self.store = store
        self.events = events or JsonEventSink()

    def _record(
        self,
        kind: DraftKind,
        result: DraftEnvelope,
        started: float,
    ) -> DraftEnvelope:
        self.events.emit(
            kind.value,
            result.status,
            (monotonic() - started) * 1_000,
            result.reason,
        )
        return result

    async def draft(
        self,
        kind: DraftKind,
        content: str,
        pattern: str | None = None,
    ) -> DraftEnvelope:
        started = monotonic()
        if not self.settings.enabled:
            result = DraftEnvelope(status="fallback", reason="local_delegation_disabled")
            return self._record(kind, result, started)
        try:
            packet = content if pattern is None else f"{content}\n{pattern}"
            assert_allowed_request(kind, packet)
            if len(packet) > self.settings.max_input_chars:
                raise PolicyError("input_too_large")
            safe_content = sanitize_transient(content, self.settings.max_input_chars)
            safe_pattern = (
                sanitize_transient(pattern, self.settings.max_input_chars) if pattern else None
            )
            result = await self.drafting.generate(
                build_prompt(kind, safe_content, safe_pattern)
            )
            if kind in QA_DRAFT_KINDS and not result.unverified:
                incomplete = DraftEnvelope(
                    status="fallback",
                    reason="ollama_invalid_schema",
                )
                return self._record(kind, incomplete, started)
            if result.learning_proposal:
                try:
                    self.store.add(result.learning_proposal)
                except PolicyError:
                    result.learning_proposal = None
            return self._record(kind, result, started)
        except PolicyError as exc:
            result = DraftEnvelope(status="refused", reason=exc.code)
            return self._record(kind, result, started)
        except BackendError as exc:
            result = DraftEnvelope(status="fallback", reason=exc.code)
            return self._record(kind, result, started)

    def list_proposals(self) -> list[LearningProposal]:
        return self.store.list_pending()

    async def approve_proposal(self, proposal_id: str) -> LearningEnvelope:
        proposal = self.store.get_pending(proposal_id)
        try:
            await self.learning.apply(proposal.text)
        except BackendError as exc:
            return LearningEnvelope(status="fallback", reason=exc.code)
        approved = self.store.approve(proposal_id)
        return LearningEnvelope(status="approved", proposal=approved)

    def reject_proposal(self, proposal_id: str) -> bool:
        return self.store.reject(proposal_id)
