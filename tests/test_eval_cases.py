import json
from pathlib import Path

import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore

CASES_PATH = Path(__file__).parent / "eval_cases.json"


class EvalDraftBackend:
    def __init__(self, case):
        self.case = case

    async def generate(self, prompt):
        if code := self.case.get("backend_error"):
            raise BackendError(code)
        return DraftEnvelope(
            draft="Synthetic draft",
            unverified=["Codex review required"],
            learning_proposal=self.case.get("proposal"),
        )


class EvalLearningBackend:
    async def apply(self, text):
        return "stored"


def load_cases():
    return json.loads(CASES_PATH.read_text())


def test_eval_set_contains_required_policy_and_fallback_categories():
    cases = load_cases()

    assert len(cases) == 9
    assert {case["expected"] for case in cases} == {"ok", "refused", "fallback"}
    assert {case["name"] for case in cases} == {
        "case_draft",
        "checklist",
        "duplicate_case",
        "log_group",
        "wdio_skeleton",
        "severity",
        "secret",
        "forbidden_learning",
        "outage",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    json.loads(CASES_PATH.read_text()) if CASES_PATH.exists() else [],
    ids=lambda case: case["name"],
)
async def test_synthetic_eval_case(case, tmp_path):
    data_dir = tmp_path / case["name"]
    store = ProposalStore(data_dir)
    service = RouterService(
        Settings(data_dir=data_dir),
        EvalDraftBackend(case),
        EvalLearningBackend(),
        store,
    )

    result = await service.draft(
        DraftKind(case["kind"]),
        case["input"],
        case.get("pattern"),
    )

    assert result.status == case["expected"]
    if case["name"] == "forbidden_learning":
        assert result.learning_proposal is None
        assert store.list_pending() == []
