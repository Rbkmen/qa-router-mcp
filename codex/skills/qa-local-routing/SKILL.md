---
name: qa-local-routing
description: Use when a request has already been reduced to bounded sanitized text and only needs routine translation, rewriting, a short explanation, source-bound summarization, test-case drafting, visible log-signature grouping, or a non-writing automation skeleton.
---

# QA Local Routing

Use the local router only after Codex has selected the smallest relevant input packet.

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

## Learning

Never send transient task content to Hermes. Gemma handles drafts directly. Show a generic learning proposal only when useful; call `approve_learning_proposal` only after explicit user approval. Otherwise leave it pending or reject it.
