import os
from dataclasses import replace
from pathlib import Path

import pytest

from qa_router_mcp.backends import LMStudioDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.service import RouterService


@pytest.fixture
async def live_service(tmp_path):
    data_dir = Path(os.environ.get("QA_ROUTER_DATA_DIR", tmp_path))
    settings = replace(Settings.from_env(), data_dir=data_dir, metrics_source="benchmark")
    backend = LMStudioDraftBackend(settings)
    try:
        yield RouterService(settings, backend)
    finally:
        await backend.client.aclose()


pytestmark = pytest.mark.skipif(
    os.environ.get("QA_ROUTER_EXTENDED") != "1",
    reason="opt-in extended benchmark against local LM Studio",
)


@pytest.mark.asyncio
async def test_eight_focused_cases(live_service):
    result = await live_service.draft(
        DraftKind.TEST_CASES,
        (
            "Synthetic requirement: a profile form contains Display name, Locale, and "
            "Time zone. Save accepts valid values, keeps unchanged values, rejects an empty "
            "Display name, rejects a name over 80 characters, preserves Unicode, prevents a "
            "duplicate submit, shows field validation, and allows Cancel without saving. "
            "Draft exactly eight focused test cases, one for each listed behavior."
        ),
    )

    assert result.status == "ok", result.reason
    assert result.draft.count("Title:") == 8


@pytest.mark.asyncio
async def test_large_visible_log_group(live_service):
    lines = (
        ["ERROR synthetic_timeout operation=profile_read"] * 360
        + ["WARN synthetic_retry attempt=2"] * 240
        + ["INFO synthetic_success status=200"] * 180
    )
    content = "Group only the visible signatures and counts.\n" + "\n".join(lines)
    assert 20_000 < len(content) < 40_000

    result = await live_service.draft(DraftKind.LOG_SUMMARY, content)

    assert result.status == "ok", result.reason
    assert result.draft.strip()


@pytest.mark.asyncio
async def test_large_source_bound_summary(live_service):
    facts = [
        f"Fact {index}: synthetic component C{index % 7} changed flag F{index % 11}."
        for index in range(1, 350)
    ]
    content = "Summarize only the supplied facts by component.\n" + "\n".join(facts)
    assert 16_000 < len(content) < 24_000

    result = await live_service.draft(DraftKind.TEXT_SUMMARY, content)

    assert result.status == "ok", result.reason
    assert result.draft.strip()
