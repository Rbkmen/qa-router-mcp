import os
import random
import string
from dataclasses import replace
from pathlib import Path

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
    data_dir = Path(os.environ.get("QA_ROUTER_DATA_DIR", tmp_path))
    settings = replace(Settings.from_env(), data_dir=data_dir, metrics_source="smoke")
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
    dense_ascii = "".join(random.Random(42).choices(string.ascii_letters + string.digits, k=20_000))
    context_refusal = await service.draft(DraftKind.TEST_CASES, dense_ascii)

    assert draft.status == "ok"
    assert draft.draft.count("Title:") >= 3
    assert "Steps:" in draft.draft
    assert "Expected Result:" in draft.draft
    assert isinstance(draft.unverified, list)
    assert refusal.status == "refused"
    assert refusal.reason == "secret_detected"
    assert context_refusal.status == "refused"
    assert context_refusal.reason == "token_budget_exceeded"
    assert '"source":"smoke"' in settings.metrics_path.read_text()
    await drafting.client.aclose()
