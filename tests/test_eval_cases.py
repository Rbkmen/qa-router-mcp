import json
from pathlib import Path

import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.service import RouterService
from qa_router_mcp.validation import requested_case_count

CASES_PATH = Path(__file__).parent / "eval_cases.json"


class EvalDraftBackend:
    def __init__(self, case):
        self.case = case

    async def count_tokens(self, prompt):
        return 100

    async def generate(self, prompt, *, max_output_tokens=None, allow_schema_repair=True):
        if code := self.case.get("backend_error"):
            raise BackendError(code)
        draft = "Synthetic draft"
        if self.case["kind"] == "test_cases":
            draft = "\n\n".join(
                (
                    f"Title: Synthetic case {number}\nPreconditions: Ready\n"
                    "Steps: 1. Act\nExpected Result: Expected behavior"
                )
                for number in range(
                    1,
                    requested_case_count(self.case["input"]) + 1,
                )
            )
        return DraftEnvelope(
            draft=draft,
            unverified=["Codex review required"],
        )


def load_cases():
    return json.loads(CASES_PATH.read_text())


def test_eval_set_contains_required_policy_and_fallback_categories():
    cases = load_cases()

    assert len(cases) == 31
    assert {case["expected"] for case in cases} == {"ok", "refused", "fallback"}
    ok_kinds = [case["kind"] for case in cases if case["expected"] == "ok"]
    assert {kind: ok_kinds.count(kind) for kind in set(ok_kinds)} == {
        kind.value: 4 for kind in DraftKind
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    json.loads(CASES_PATH.read_text()) if CASES_PATH.exists() else [],
    ids=lambda case: case["name"],
)
async def test_synthetic_eval_case(case, tmp_path):
    data_dir = tmp_path / case["name"]
    service = RouterService(
        Settings(data_dir=data_dir),
        EvalDraftBackend(case),
    )

    result = await service.draft(
        DraftKind(case["kind"]),
        case["input"],
        case.get("pattern"),
    )

    assert result.status == case["expected"]
