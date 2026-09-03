---
name: qa-local-routing
description: Use when a request has already been reduced to bounded sanitized text and only needs routine translation, rewriting, a short explanation, source-bound summarization, test-case drafting, visible log-signature grouping, or a non-writing automation skeleton.
---

# QA Local Routing

Use only `qwen/qwen3.5-9b` after Codex selects the smallest relevant sanitized packet. Local output is an unverified draft, not a decision.

## Route automatically

- `draft_test_cases`: 4–12 approved coverage-map items, exactly one per requested case.
- `summarize_logs`: at least 6,000 characters; group visible signatures only.
- `summarize_text`: at least 4,000 characters; use only supplied facts.
- `translate_text` or `rewrite_text`: at least 2,000 characters.
- `draft_automation_skeleton`: an explicit project pattern and a multi-step scenario.

Keep smaller tasks in Terra. Use `explain_short` only when the user explicitly requests local Qwen. An explicit local-model request may override the size threshold when policy permits.

## Review and canary

Treat every result as a draft. Verify all `assumptions` and `unverified` items.

For test cases, Terra must first decide final coverage and create one concise item per case with purpose, confirmed source, state/branch, and expected invariant. Call `draft_test_cases(requirement=<sanitized bounded requirement>, coverage_map=[<one item per case>], examples=<optional project style>)`. Qwen only expands that fixed map into case prose; it must not add, remove, merge, reprioritize, or select coverage. Compare the result item-by-item before accepting it.

When `canary_feedback_required` is true, call `record_canary_feedback` exactly once after review:

- unchanged draft: `accepted` + `none`;
- corrected draft: `edited` + the main reason;
- discarded draft: `rejected` + the main reason.

Call `record_canary_feedback(draft_id=<returned ID>, verdict=<verdict>, reason=<reason>)`; these are the only arguments. Never invent or reuse an ID, and do not submit feedback when `canary_feedback_required` is false. Stored feedback contains only the random ID, derived route kind, verdict, and reason—never task or draft text.

Each profile version has a 50-review canary with fixed quotas: 15 test-case, 10 log, 10 automation, 10 summary, 3 rewrite, and 2 translation drafts. A route stops requesting feedback when the current profile's quota is full.

## Keep in Codex

Codex owns Jira/MR/diff analysis, current facts, the Evidence Packet, final coverage, severity, release readiness, code changes, QA outcome metrics, and every external-system action. Continue in Terra when local routing refuses or falls back.

Never include credentials, cookies, tokens, personal or payment data, complete repositories, or unrestricted corporate documents.
If a local route refuses with `sensitive_data_detected`, reduce and sanitize the packet in Codex; do not weaken or bypass the check.

## Persistence

The local route is stateless at the application level. Do not create learning proposals, persistent model memory, or local copies of Jira, TestRail, source repositories, logs, or corporate documents.
