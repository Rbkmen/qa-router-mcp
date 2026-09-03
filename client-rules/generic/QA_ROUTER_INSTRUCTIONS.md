# QA Router host-agent instructions

Use the `qa-router` MCP server only for bounded, sanitized routine drafts.

- The host agent owns source retrieval, analysis, final QA judgment, code and file changes, and every external-system write.
- Route automatically only for 4–12 approved test cases, logs from 6,000 characters, source-bound summaries from 4,000 characters, translations or rewrites from 2,000 characters, or an automation skeleton with an explicit project pattern and multi-step scenario.
- Send only the smallest sufficient sanitized packet. Never send secrets, personal or payment data, full repositories, full conversation history, unrestricted corporate documents, or raw external-system payloads.
- Treat every local result as an unverified draft. Validate it against authoritative evidence before returning a final result.
- If the router refuses or falls back, continue in the host agent without weakening policy checks or retrying in a loop.
- If `canary_feedback_required` is true, call `record_canary_feedback` exactly once after reviewing the returned draft.
- Do not create persistent QA memory or a learning layer around the router.
