---
name: qa-local-routing
description: Use when a request has already been reduced to bounded sanitized text and only needs routine translation, rewriting, a short explanation, source-bound summarization, test-case drafting, visible log-signature grouping, or a non-writing automation skeleton.
---

# QA Local Routing

Use the local router backed only by `qwen/qwen3.5-9b` after Codex has selected the smallest relevant input packet. Do not select or introduce another local model or fallback model.

## Delegate locally

- `draft_test_cases`: focused case or checklist drafts.
- `summarize_logs`: grouping by visible signature without root-cause claims.
- `draft_automation_skeleton`: a skeleton based on an explicit supplied pattern.
- `translate_text`: bounded translation with explicitly preserved terms.
- `rewrite_text`: shorten, correct, or restyle supplied text without changing facts.
- `explain_short`: brief stable explanation that does not need research or citations.
- `summarize_text`: source-bound summary with an optional focus.

Treat every result as a draft. Verify all `assumptions` and `unverified` items.

## Keep in Codex

Codex remains responsible for Jira/MR/diff analysis, CodeGraph navigation, current or uncertain facts, research and citations, final coverage, severity, release readiness, code changes, and every external-system action. Continue in Codex when the router refuses, times out, or returns fallback.

Never include credentials, cookies, tokens, personal or payment data, complete repositories, or unrestricted corporate documents.

## Persistence

The local route is stateless at the application level. Do not create learning proposals, persistent model memory, or local copies of Jira, TestRail, source repositories, logs, or corporate documents.
