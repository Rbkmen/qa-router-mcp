# Cursor setup

Cursor supports local STDIO MCP servers through `mcp.json`. Use `$HOME/.cursor/mcp.json` for all projects or `.cursor/mcp.json` in one project.

## Connect the server

Create or merge this configuration without overwriting existing servers:

```json
{
  "mcpServers": {
    "qa-router": {
      "command": "/absolute/path/to/qa-router-mcp/scripts/qa-router-mcp",
      "args": []
    }
  }
}
```

Restart Cursor and check the MCP settings. Cursor Agent exposes connected MCP tools under Available Tools.

## Install the routing rule

```bash
mkdir -p /absolute/path/to/your-project/.cursor/rules
cp /absolute/path/to/qa-router-mcp/client-rules/cursor/qa-router.mdc \
  /absolute/path/to/your-project/.cursor/rules/qa-router.mdc
```

The `.mdc` template is an always-applied project rule. It adapts the shared [QA Router policy](../ROUTING_POLICY.md) without assuming a specific Cursor model.

For a personal rule across projects, add the same instructions through Cursor Settings → Rules → User Rules.

The rule handles stable coverage IDs, per-tool quality states, 10% independent shadow checks, content-free draft feedback, and one content-free outcome record per finished QA task.

References: [official Cursor MCP documentation](https://docs.cursor.com/context/model-context-protocol) and [official Cursor Rules documentation](https://cursor.com/docs/rules).
