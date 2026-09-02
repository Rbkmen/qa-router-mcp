---
name: qa-local-routing
description: Use when a request has already been reduced to bounded sanitized text and only needs routine translation, rewriting, a short explanation, source-bound summarization, test-case drafting, visible log-signature grouping, or a non-writing automation skeleton.
---

# QA Local Routing

Use only `qwen/qwen3.5-9b` after Codex selects the smallest relevant sanitized packet. Local output is an unverified draft, not a decision.

## Route automatically

- `draft_test_cases`: 4–12 requested cases.
- `summarize_logs`: at least 6,000 characters; group visible signatures only.
- `summarize_text`: at least 4,000 characters; use only supplied facts.
- `translate_text` or `rewrite_text`: at least 2,000 characters.
- `draft_automation_skeleton`: an explicit project pattern and a multi-step scenario.

Keep smaller tasks in Terra. Use `explain_short` only when the user explicitly requests local Qwen. An explicit local-model request may override the size threshold when policy permits.

## Review and canary

Treat every result as a draft. Verify all `assumptions` and `unverified` items.

When `canary_feedback_required` is true, call `record_canary_feedback` exactly once after review:

- unchanged draft: `accepted` + `none`;
- corrected draft: `edited` + the main reason;
- discarded draft: `rejected` + the main reason.

Feedback contains only route kind, verdict, and reason—never task or draft text. The router stops requesting feedback after 50 reviews.

## Keep in Codex

Codex owns Jira/MR/diff analysis, current facts, evidence, final coverage, severity, release readiness, code changes, and every external-system action. Continue in Terra when local routing refuses or falls back.

Never include credentials, cookies, tokens, personal or payment data, complete repositories, or unrestricted corporate documents.

## Persistence

The local route is stateless at the application level. Do not create learning proposals, persistent model memory, or local copies of Jira, TestRail, source repositories, logs, or corporate documents.
