import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from qa_router_mcp.backends import LMStudioDraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.service import RouterService

CASES_PATH = Path(__file__).parent / "eval_cases.json"
OK_CASES = [
    case
    for case in json.loads(CASES_PATH.read_text())
    if case["expected"] == "ok"
]


@pytest.mark.skipif(
    os.environ.get("QA_ROUTER_BENCHMARK") != "1",
    reason="opt-in live benchmark against local LM Studio",
)
@pytest.mark.asyncio
@pytest.mark.parametrize("case", OK_CASES, ids=lambda case: case["name"])
async def test_live_synthetic_benchmark_case(case, tmp_path):
    settings = replace(Settings.from_env(), data_dir=tmp_path)
    backend = LMStudioDraftBackend(settings)
    service = RouterService(settings, backend)

    try:
        result = await service.draft(
            DraftKind(case["kind"]),
            case["input"],
            case.get("pattern"),
        )
    finally:
        await backend.client.aclose()

    assert result.status == "ok", result.reason
