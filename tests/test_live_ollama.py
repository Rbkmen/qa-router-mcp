import os

import pytest

from qa_router_mcp.backends import HermesLearningBackend, OllamaDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


@pytest.mark.skipif(
    os.environ.get("QA_ROUTER_LIVE") != "1",
    reason="requires local Ollama and the pinned Gemma model",
)
@pytest.mark.asyncio
async def test_synthetic_draft_and_secret_refusal_against_live_ollama(tmp_path):
    settings = Settings(data_dir=tmp_path)
    drafting = OllamaDraftBackend(settings)
    service = RouterService(
        settings,
        drafting,
        HermesLearningBackend(settings),
        ProposalStore(tmp_path),
    )

    draft = await service.draft(
        DraftKind.TEST_CASES,
        "Guest checkout supports a synthetic expired-card validation example",
    )
    refusal = await service.draft(
        DraftKind.LOG_SUMMARY,
        "Authorization: Bearer synthetic-secret",
    )

    assert draft.status == "ok"
    assert draft.draft.strip()
    assert draft.unverified
    assert refusal.status == "refused"
    assert refusal.reason == "secret_detected"
    await drafting.client.aclose()
