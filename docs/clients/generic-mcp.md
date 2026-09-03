# Generic MCP client setup

QA Router uses the standard MCP STDIO transport. A compatible client must be able to start a local command, exchange MCP messages over stdin/stdout, and expose server tools to its agent.

## Generic configuration

Many MCP clients accept an `mcpServers` object similar to this:

```json
{
  "mcpServers": {
    "qa-router": {
      "command": "/absolute/path/to/qa-router-mcp/scripts/qa-router-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

The exact configuration file and schema are client-specific. Use an absolute command path because GUI applications may not inherit the same working directory or shell `PATH` as a terminal.

## Agent instructions

Copy or merge [`client-rules/generic/QA_ROUTER_INSTRUCTIONS.md`](../../client-rules/generic/QA_ROUTER_INSTRUCTIONS.md) into the client's persistent instruction mechanism. The client must apply the shared [QA Router policy](../ROUTING_POLICY.md), review every draft, and retain exclusive control over external writes.

## Verification

After configuration:

1. Confirm that the server connects and lists its tools.
2. Call `explain_short` only as an explicit smoke test with non-sensitive text.
3. Confirm that the result is shown as an unverified draft.
4. Confirm that the host agent reviews the draft before returning a final answer.
5. Confirm that the client respects `quality_status`, handles requested shadow evaluation independently, and records one content-free outcome when a QA task ends.
