import pytest
from fastmcp import Client

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
                "Title: Case\nPreconditions: Ready\nSteps: 1. Act\n"
                "Expected Result: Expected behavior"
            ),
            unverified=["Review locally"],
        )


@pytest.mark.asyncio
async def test_server_exposes_only_seven_drafting_tools(tmp_path):
    drafting = DraftFake()
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    async with Client(build_server(service)) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert names == {
            "draft_test_cases",
            "summarize_logs",
            "draft_automation_skeleton",
            "translate_text",
            "rewrite_text",
            "explain_short",
            "summarize_text",
        }

        result = await client.call_tool(
            "draft_test_cases",
            {"requirement": "Guest checkout"},
        )
        assert result.structured_content["status"] == "ok"


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
