import os
import subprocess
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/qa-router-mcp"

CLIENT_ARTIFACTS = {
    "docs/ROUTING_POLICY.md": ["host agent", "record_canary_feedback"],
    "docs/clients/codex.md": ["codex mcp add", "qa-local-routing"],
    "docs/clients/claude-code.md": ["claude mcp add", "CLAUDE.md"],
    "docs/clients/cursor.md": [".cursor/mcp.json", "qa-router.mdc"],
    "docs/clients/generic-mcp.md": ["STDIO", "mcpServers"],
    "client-rules/claude-code/CLAUDE.md": ["QA Router", "unverified draft"],
    "client-rules/cursor/qa-router.mdc": ["alwaysApply: true", "QA Router"],
    "client-rules/generic/QA_ROUTER_INSTRUCTIONS.md": ["QA Router", "host agent"],
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


def test_client_guides_and_rule_templates_are_distributed():
    for relative_path, required_fragments in CLIENT_ARTIFACTS.items():
        artifact = ROOT / relative_path
        assert artifact.is_file(), f"missing {relative_path}"
        content = artifact.read_text(encoding="utf-8")
        for fragment in required_fragments:
            assert fragment in content, f"{fragment!r} missing from {relative_path}"


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
