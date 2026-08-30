from fastmcp import FastMCP

from qa_router_mcp.backends import HermesLearningBackend, OllamaDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import (
    DraftEnvelope,
    DraftKind,
    LearningEnvelope,
    LearningProposal,
)
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


def build_server(service: RouterService) -> FastMCP:
    mcp = FastMCP(name="qa-router-mcp")

    @mcp.tool
    async def draft_test_cases(
        requirement: str,
        examples: str = "",
    ) -> DraftEnvelope:
        """Draft focused unverified test cases from a bounded sanitized requirement."""
        content = requirement if not examples else f"{requirement}\nEXAMPLES:\n{examples}"
        return await service.draft(DraftKind.TEST_CASES, content)

    @mcp.tool
    async def summarize_logs(logs: str) -> DraftEnvelope:
        """Group sanitized log fragments by visible signature without root-cause decisions."""
        return await service.draft(DraftKind.LOG_SUMMARY, logs)

    @mcp.tool
    async def draft_automation_skeleton(
        scenario: str,
        pattern: str,
    ) -> DraftEnvelope:
        """Draft a non-writing automation skeleton from an explicit supplied pattern."""
        return await service.draft(DraftKind.AUTOMATION_SKELETON, scenario, pattern)

    @mcp.tool
    async def translate_text(
        text: str,
        target_language: str,
        preserve_terms: str = "",
    ) -> DraftEnvelope:
        """Translate bounded sanitized text while preserving explicitly supplied terms."""
        content = f"TARGET_LANGUAGE:\n{target_language}\nTEXT:\n{text}"
        if preserve_terms:
            content += f"\nPRESERVE_TERMS:\n{preserve_terms}"
        return await service.draft(DraftKind.TRANSLATION, content)

    @mcp.tool
    async def rewrite_text(text: str, instruction: str) -> DraftEnvelope:
        """Rewrite bounded sanitized text without adding facts."""
        content = f"INSTRUCTION:\n{instruction}\nTEXT:\n{text}"
        return await service.draft(DraftKind.REWRITE, content)

    @mcp.tool
    async def explain_short(
        topic: str,
        audience: str = "QA engineer",
    ) -> DraftEnvelope:
        """Draft a short non-researched explanation for the requested audience."""
        content = f"AUDIENCE:\n{audience}\nTOPIC:\n{topic}"
        return await service.draft(DraftKind.SHORT_EXPLANATION, content)

    @mcp.tool
    async def summarize_text(text: str, focus: str = "") -> DraftEnvelope:
        """Summarize only bounded sanitized supplied text without adding facts."""
        content = f"TEXT:\n{text}"
        if focus:
            content = f"FOCUS:\n{focus}\n{content}"
        return await service.draft(DraftKind.TEXT_SUMMARY, content)

    @mcp.tool
    def list_learning_proposals() -> list[LearningProposal]:
        """List sanitized pending proposals for explicit user review."""
        return service.list_proposals()

    @mcp.tool
    async def approve_learning_proposal(
        proposal_id: str,
        user_confirmed: bool,
    ) -> LearningEnvelope:
        """Approve one reviewed proposal and send only its validated text to Hermes."""
        if not user_confirmed:
            return LearningEnvelope(
                status="fallback",
                reason="explicit_approval_required",
            )
        return await service.approve_proposal(proposal_id)

    @mcp.tool
    def reject_learning_proposal(proposal_id: str) -> bool:
        """Delete one pending proposal without sending it to Hermes."""
        return service.reject_proposal(proposal_id)

    return mcp


def main() -> None:
    settings = Settings.from_env()
    service = RouterService(
        settings,
        OllamaDraftBackend(settings),
        HermesLearningBackend(settings),
        ProposalStore(settings.data_dir),
    )
    build_server(service).run()
