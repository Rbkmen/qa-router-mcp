# Claude Code setup

Claude Code can run QA Router as a local STDIO MCP server. Use user scope to make it available across projects, or local scope for a single project.

## Connect the server

```bash
claude mcp add --transport stdio --scope user qa-router -- \
  /absolute/path/to/qa-router-mcp/scripts/qa-router-mcp
```

Verify the connection:

```bash
claude mcp get qa-router
claude mcp list
```

Inside Claude Code, `/mcp` also shows the server status and tools.

## Install the routing instructions

For a new project without a `CLAUDE.md`:

```bash
cp /absolute/path/to/qa-router-mcp/client-rules/claude-code/CLAUDE.md \
  /absolute/path/to/your-project/CLAUDE.md
```

If the project already has a `CLAUDE.md`, merge the contents instead of overwriting it. The template adapts the shared [QA Router policy](../ROUTING_POLICY.md) to Claude Code.

Claude Code has no Codex-specific Terra/Sol routing requirement. The active Claude model is the host agent; any Claude subagent is client-owned and must remain outside QA Router.

The template handles stable coverage IDs, per-tool quality states, required feedback for each new profile, 10% independent shadow checks, content-free draft feedback, and one content-free outcome record per finished QA task.

Reference: [official Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).
