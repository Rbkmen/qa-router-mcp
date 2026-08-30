import pytest
from fastmcp import Client

from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope
from qa_router_mcp.server import build_server
from qa_router_mcp.service import RouterService
from qa_router_mcp.store import ProposalStore


class DraftFake:
    async def generate(self, prompt):
        return DraftEnvelope(draft="Case", unverified=["Review locally"])


class LearningFake:
    async def apply(self, text):
        return "stored"


@pytest.mark.asyncio
async def test_server_exposes_only_six_narrow_tools(tmp_path):
    service = RouterService(
        Settings(data_dir=tmp_path),
        DraftFake(),
        LearningFake(),
        ProposalStore(tmp_path),
    )

    async with Client(build_server(service)) as client:
        names = {tool.name for tool in await client.list_tools()}
        assert names == {
            "draft_test_cases",
            "summarize_logs",
            "draft_automation_skeleton",
            "list_learning_proposals",
            "approve_learning_proposal",
            "reject_learning_proposal",
        }

        result = await client.call_tool(
            "draft_test_cases",
            {"requirement": "Guest checkout"},
        )
        assert result.structured_content["status"] == "ok"

        refusal = await client.call_tool(
            "approve_learning_proposal",
            {"proposal_id": "lp_missing", "user_confirmed": False},
        )
        assert refusal.structured_content["reason"] == "explicit_approval_required"
