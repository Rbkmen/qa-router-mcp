# QA Router usage

When the `qa-router` MCP server is available, use it only for bounded, sanitized routine drafts. Follow the repository's QA Router policy.

- Keep source retrieval, analysis, final QA judgment, code and file changes, and all external-system writes in Claude Code.
- Route automatically only for 4–12 approved test cases, logs from 6,000 characters, source-bound summaries from 4,000 characters, translations or rewrites from 2,000 characters, or an automation skeleton with an explicit project pattern and multi-step scenario.
- Before calling a router tool, send only the smallest sufficient sanitized packet. Never send secrets, personal or payment data, full repositories, full chat history, unrestricted corporate documents, or raw external-system payloads.
- Treat every Qwen result as an unverified draft. Compare it with authoritative evidence, remove unsupported facts, and make the final decision yourself.
- If the router refuses or falls back, continue in Claude Code. Do not weaken policy checks or retry in a loop.
- If `canary_feedback_required` is true, review the draft and call `record_canary_feedback` exactly once with its returned `draft_id`.
- For test cases, send unique stable `COV-*` coverage IDs with purpose, source, state, and expected invariant; require every ID exactly once in the result.
- Respect `quality_status`: use `active`, review `canary`, and continue in Claude Code when `paused`.
- If `shadow_evaluation_required` is true, create an independent Claude baseline from the same sanitized packet before using the Qwen draft, compare them, then record feedback. The router never calls Claude itself.
- After every completed, partial, or blocked QA task, call `record_qa_task_outcome` exactly once with content-free counters only.
- Do not add persistent QA memory or a learning layer around the router.
