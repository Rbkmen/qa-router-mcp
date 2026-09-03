# QA Router Policy

This policy is client-neutral. In this document, **host agent** means Codex, Claude Code, Cursor Agent, or another MCP-capable AI that calls QA Router.

## Responsibility boundary

The host agent owns:

- task classification and source retrieval;
- requirement, code, diff, and log analysis;
- the final coverage map, risk, severity, and release judgment;
- all code and file changes;
- all writes to Jira, GitLab, TestRail, Sentry, or any other external system;
- review and correction of every local draft.

Qwen3.5-9B produces bounded drafts only. Its output is never evidence, a final QA decision, or authorization for an external action.

## Automatic routing thresholds

Use QA Router automatically only for:

- 4–12 test cases based on a coverage map already approved by the host agent;
- sanitized logs containing at least 6,000 characters;
- source-bound summaries containing at least 4,000 characters;
- translations or rewrites containing at least 2,000 characters;
- automation skeletons with an explicit project pattern and a multi-step scenario.

Keep smaller tasks in the host agent. Use `explain_short` locally only when the user explicitly requests the local model. An explicit request may override a size threshold, but never a security or validation rule.

## Data minimization

Before every local call, the host agent must prepare the smallest sufficient packet.

Never send:

- credentials, cookies, tokens, or private keys;
- personal, session, identity, or payment data;
- unrestricted corporate documents;
- complete repositories or full chat history;
- raw external-system payloads;
- raw QA logs before reduction and sanitization.

If the router returns `sensitive_data_detected`, reduce and sanitize the packet. Never weaken or bypass the policy check.

## Tool selection

- `draft_test_cases`: expand an approved 1–12 item coverage map. Each item must contain one purpose, confirmed source, state or branch, and expected invariant.
- `summarize_logs`: group only visible signatures. Do not accept an inferred root cause without separate evidence.
- `draft_automation_skeleton`: draft structure from an explicit project pattern. The tool must not write files or external data.
- `translate_text`: translate sanitized text while preserving supplied terminology.
- `rewrite_text`: shorten, correct, or restyle supplied text without adding facts.
- `summarize_text`: summarize only supplied source material.
- `explain_short`: explain stable, non-researched material only after an explicit local-model request.

## Review contract

After every successful draft:

1. Compare it with the bounded input and authoritative evidence.
2. Remove unsupported facts, invented behavior, missing branches, and merged scenarios.
3. Keep assumptions and unverifiable statements explicitly marked.
4. Return only the host agent's reviewed result to the user.

If `canary_feedback_required` is true, call `record_canary_feedback` exactly once with the returned `draft_id`:

- unchanged: `accepted` and `none`;
- corrected: `edited` and the primary correction category;
- discarded: `rejected` and the primary rejection category.

Do not invent, reuse, or persist draft IDs. If the router refuses or falls back, continue in the host agent without retry loops.

## Optional deep analysis

Deep-analysis agents are client-owned and are not part of QA Router. A host may use one bounded read-only specialist for difficult cross-repository reasoning, conflicting evidence, security-sensitive work, or high-blast-radius edge cases. The host still makes the final decision.

## Persistence

QA Router is stateless at the application level. Do not add a learning layer, persistent model memory, or local copies of source-system content.
