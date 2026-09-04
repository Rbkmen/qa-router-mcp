import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope
from qa_router_mcp.server import build_server
from qa_router_mcp.service import RouterService


class DraftFake:
    def __init__(self):
        self.prompts = []

    async def count_tokens(self, prompt):
        return 100

    async def generate(self, prompt, *, max_output_tokens=None, allow_schema_repair=True):
        self.prompts.append(prompt)
        return DraftEnvelope(
            draft=(
                "Coverage ID: COV-GUEST-HAPPY\nTitle: Case\n"
                "Preconditions: Ready\nSteps: 1. Act\n"
                "Expected Result: Expected behavior"
            ),
            unverified=["Review locally"],
        )


@pytest.mark.asyncio
async def test_server_exposes_drafting_and_metrics_tools(tmp_path):
    drafting = DraftFake()
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    async with Client(build_server(service)) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        names = set(tools)
        assert names == {
            "draft_test_cases",
            "summarize_logs",
            "draft_automation_skeleton",
            "translate_text",
            "rewrite_text",
            "explain_short",
            "summarize_text",
            "record_canary_feedback",
            "record_qa_task_outcome",
        }
        outcome_fields = tools["record_qa_task_outcome"].inputSchema["properties"]
        assert {
            "codegraph_response_tokens",
            "source_mcp_response_tokens",
            "avoided_source_read_tokens",
        } <= outcome_fields.keys()

        result = await client.call_tool(
            "draft_test_cases",
            {
                "requirement": "Guest checkout",
                "coverage_map": [
                    {
                        "coverage_id": "COV-GUEST-HAPPY",
                        "purpose": "Happy path",
                        "source": "Confirmed requirement",
                        "state": "Guest checkout",
                        "expected_invariant": "Checkout is submitted",
                    }
                ],
            },
        )
        assert result.structured_content["status"] == "ok"
        assert "APPROVED_COVERAGE_MAP" in drafting.prompts[0]
        assert "Coverage ID: COV-GUEST-HAPPY" in drafting.prompts[0]
        assert "Expected invariant: Checkout is submitted" in drafting.prompts[0]
        assert result.structured_content["quality_status"] == "canary"

        feedback = await client.call_tool(
            "record_canary_feedback",
            {
                "draft_id": result.structured_content["draft_id"],
                "verdict": "edited",
                "reason": "coverage",
            },
        )
        assert feedback.structured_content == {
            "status": "recorded",
            "feedback_count": 1,
            "target": 50,
        }

        task_outcome = await client.call_tool(
            "record_qa_task_outcome",
            {
                "task_type": "ordinary_review",
                "outcome": "completed",
                "codegraph_calls": 1,
                "source_mcp_calls": 4,
                "qwen_used": True,
                "sol_used": False,
                "findings_identified": 2,
                "findings_confirmed": 1,
                "findings_rejected": 1,
                "qwen_edits": 1,
                "repeated_source_reads": 0,
            },
        )
        assert task_outcome.structured_content == {"status": "recorded"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "prompt_markers"),
    [
        (
            "translate_text",
            {
                "text": "Check guest checkout",
                "target_language": "Russian",
                "preserve_terms": "checkout",
            },
            ("Check guest checkout", "Russian", "checkout"),
        ),
        (
            "rewrite_text",
            {"text": "The test has failed", "instruction": "Make it concise"},
            ("The test has failed", "Make it concise"),
        ),
        (
            "explain_short",
            {"topic": "What is idempotency?", "audience": "QA engineer"},
            ("What is idempotency?", "QA engineer", "120 words"),
        ),
        (
            "summarize_text",
            {"text": "First fact. Second fact.", "focus": "Risks"},
            ("First fact. Second fact.", "Risks"),
        ),
    ],
)
async def test_text_tools_pass_bounded_instructions_to_local_backend(
    tmp_path,
    tool_name,
    arguments,
    prompt_markers,
):
    drafting = DraftFake()
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    async with Client(build_server(service)) as client:
        result = await client.call_tool(tool_name, arguments)

    assert result.structured_content["status"] == "ok"
    assert all(marker in drafting.prompts[0] for marker in prompt_markers)


@pytest.mark.asyncio
async def test_test_case_tool_rejects_duplicate_coverage_ids(tmp_path):
    drafting = DraftFake()
    service = RouterService(Settings(data_dir=tmp_path), drafting)
    item = {
        "coverage_id": "COV-DUPLICATE",
        "purpose": "Branch",
        "source": "Confirmed requirement",
        "state": "Ready",
        "expected_invariant": "Stable result",
    }

    async with Client(build_server(service)) as client:
        with pytest.raises(ToolError, match="coverage IDs must be unique"):
            await client.call_tool(
                "draft_test_cases",
                {"requirement": "Requirement", "coverage_map": [item, item]},
            )
