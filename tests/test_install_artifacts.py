import os
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/qa-router-mcp"

CLIENT_ARTIFACTS = {
    "docs/ROUTING_POLICY.md": [
        "host agent",
        "record_canary_feedback",
        "record_qa_task_outcome",
        "shadow_evaluation_required",
    ],
    "docs/clients/codex.md": ["codex mcp add", "qa-local-routing"],
    "docs/clients/claude-code.md": ["claude mcp add", "CLAUDE.md"],
    "docs/clients/cursor.md": [".cursor/mcp.json", "qa-router.mdc"],
    "docs/clients/generic-mcp.md": ["STDIO", "mcpServers"],
    "client-rules/claude-code/CLAUDE.md": [
        "QA Router",
        "unverified draft",
        "record_qa_task_outcome",
        "shadow_evaluation_required",
    ],
    "client-rules/cursor/qa-router.mdc": [
        "alwaysApply: true",
        "QA Router",
        "record_qa_task_outcome",
        "shadow_evaluation_required",
    ],
    "client-rules/generic/QA_ROUTER_INSTRUCTIONS.md": [
        "QA Router",
        "host agent",
        "record_qa_task_outcome",
        "shadow_evaluation_required",
    ],
    "codex/skills/qa-local-routing/SKILL.md": [
        "record_qa_task_outcome",
        "shadow_evaluation_required",
        "coverage_id",
    ],
}


def test_launcher_is_executable_valid_shell():
    result = subprocess.run(
        ["/bin/sh", "-n", str(LAUNCHER)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert os.access(LAUNCHER, os.X_OK)


def test_launcher_forwards_metrics_overrides():
    content = LAUNCHER.read_text(encoding="utf-8")

    assert 'QA_ROUTER_METRICS_RETENTION_DAYS="${QA_ROUTER_METRICS_RETENTION_DAYS:-30}"' in content
    assert 'QA_ROUTER_METRICS_MAX_EVENTS="${QA_ROUTER_METRICS_MAX_EVENTS:-10000}"' in content


def test_client_guides_and_rule_templates_are_distributed():
    for relative_path, required_fragments in CLIENT_ARTIFACTS.items():
        artifact = ROOT / relative_path
        assert artifact.is_file(), f"missing {relative_path}"
        content = artifact.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in content, f"{fragment!r} missing from {relative_path}"


def test_routing_artifacts_use_expanded_local_draft_thresholds():
    required_fragments = {
        "2–12 approved test cases",
        "3,000 characters",
        "2,000 characters",
        "1,000 characters",
    }
    artifacts = (
        "README.md",
        "docs/ROUTING_POLICY.md",
        "codex/skills/qa-local-routing/SKILL.md",
        "client-rules/claude-code/CLAUDE.md",
        "client-rules/cursor/qa-router.mdc",
        "client-rules/generic/QA_ROUTER_INSTRUCTIONS.md",
    )

    for relative_path in artifacts:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in content, f"{fragment!r} missing from {relative_path}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/assets/qa-router-workflow.svg" in readme
    assert "Download PNG" not in readme


@pytest.mark.asyncio
async def test_launcher_starts_without_resolving_offline_dependencies():
    transport = StdioTransport(command=str(LAUNCHER), args=[])

    try:
        async with Client(transport) as client:
            names = {tool.name for tool in await client.list_tools()}
    finally:
        await transport.close()

    assert {
        "translate_text",
        "rewrite_text",
        "explain_short",
        "summarize_text",
    } <= names
