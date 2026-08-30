---
name: qa-local-routing
description: Use when a QA request has already been reduced to a bounded sanitized packet and only needs routine test-case drafting, visible log-signature grouping, or a non-writing automation skeleton.
---

# QA Local Routing

Use the local router only after Codex has selected the smallest relevant input packet.

## Delegate locally

- `draft_test_cases`: focused case or checklist drafts.
- `summarize_logs`: grouping by visible signature without root-cause claims.
- `draft_automation_skeleton`: a skeleton based on an explicit supplied pattern.

Treat every result as a draft. Verify all `assumptions` and `unverified` items.

## Keep in Codex

Codex remains responsible for Jira/MR/diff analysis, CodeGraph navigation, final coverage, severity, release readiness, code changes, and every external-system action. Continue in Codex when the router refuses, times out, or returns fallback.

Never include credentials, cookies, tokens, personal or payment data, complete repositories, or unrestricted corporate documents.

## Learning

Never send transient task content to Hermes. Gemma handles drafts directly. Show a generic learning proposal only when useful; call `approve_learning_proposal` only after explicit user approval. Otherwise leave it pending or reject it.
