# Codex setup

Codex supports local STDIO MCP servers through its CLI and `config.toml`. The Codex app, CLI, and IDE extension share the configuration on the same host.

## Connect the server

From the cloned repository, get its absolute path:

```bash
pwd
```

Add the server through the CLI:

```bash
codex mcp add qa-router -- \
  /absolute/path/to/qa-router-mcp/scripts/qa-router-mcp
```

Alternatively, add this block to `$HOME/.codex/config.toml`:

```toml
[mcp_servers.qa-router]
command = "/absolute/path/to/qa-router-mcp/scripts/qa-router-mcp"
args = []
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Verify the registration:

```bash
codex mcp list
```

Restart Codex after changing the configuration.

## Install the routing skill

```bash
mkdir -p "$HOME/.codex/skills/qa-local-routing"
cp codex/skills/qa-local-routing/SKILL.md \
  "$HOME/.codex/skills/qa-local-routing/SKILL.md"
```

The skill implements the shared [QA Router policy](../ROUTING_POLICY.md) for Codex. Codex remains responsible for the final result and any external write.

The installed skill also enforces stable test-case coverage IDs, per-tool quality states, 10% independent shadow checks, content-free draft feedback, and one content-free outcome record per finished QA task.

Reference: [official Codex MCP documentation](https://developers.openai.com/codex/mcp).
