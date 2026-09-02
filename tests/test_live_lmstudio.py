import os
from dataclasses import replace

import pytest

from qa_router_mcp.backends import LMStudioDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.service import RouterService


@pytest.mark.skipif(
    os.environ.get("QA_ROUTER_LIVE") != "1",
    reason="requires local LM Studio and a pinned MLX model",
)
@pytest.mark.asyncio
async def test_synthetic_draft_and_secret_refusal_against_live_lmstudio(tmp_path):
    settings = replace(Settings.from_env(), data_dir=tmp_path)
    drafting = LMStudioDraftBackend(settings)
    service = RouterService(
        settings,
        drafting,
    )

    draft = await service.draft(
        DraftKind.TEST_CASES,
        (
            "Synthetic demo: a guest checkout form accepts a valid card and shows a "
            "validation error for an expired card. Draft three focused test cases."
        ),
    )
    refusal = await service.draft(
        DraftKind.LOG_SUMMARY,
        "Authorization: Bearer synthetic-secret",
    )

    assert draft.status == "ok"
    assert draft.draft.count("Title:") >= 3
    assert "Steps:" in draft.draft
    assert "Expected Result:" in draft.draft
    assert draft.unverified
    assert refusal.status == "refused"
    assert refusal.reason == "secret_detected"
    await drafting.client.aclose()
