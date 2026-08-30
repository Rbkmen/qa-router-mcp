# QA Router MCP — Design

## Status

Approved architecture for implementation planning. This document defines a local QA delegation layer for Codex Desktop on an Apple M5 Pro MacBook Pro with 24 GB unified memory.

## Goal

Provide one-chat QA work in Codex Desktop while delegating repetitive, low-risk drafting to a local Hermes Agent backed by Gemma 4 12B. Codex remains the only user-facing orchestrator and the authority for evidence gathering, risk decisions, code changes, and external-system writes.

## Success criteria

- The user works only in Codex Desktop and does not manually choose an agent for ordinary requests.
- Codex can call the local QA specialist through one STDIO MCP server.
- Local delegation reduces cloud-model work for suitable routine tasks without weakening evidence-based QA decisions.
- Corporate credentials and corporate MCP servers are never exposed to Hermes or Ollama.
- Persistent Hermes memory contains only approved reusable procedures and formatting preferences.
- If local inference is unavailable, uncertain, or unsuitable, Codex continues the task without blocking the user.
- The setup remains usable while an IDE, browser, and normal QA tools are open on a 24 GB machine.

## Non-goals

- Replacing Codex as the primary coding and QA agent.
- Fine-tuning model weights.
- Giving Hermes direct Jira, GitLab, TestRail, Sentry, Grafana, OpenSearch, Slack, CodeGraph, shell-write, or repository-write access.
- Allowing a local model to publish, merge, transition, delete, or approve anything.
- Sending entire repositories or unrestricted corporate documents into a local prompt.
- Supporting multiple local model families in the first version.

## Architecture

```text
User
  |
  v
Codex Desktop
  |-- corporate MCP + CodeGraph + repository tools (Codex only)
  |
  `-- qa-router-mcp (local STDIO)
         |
         `-- Hermes profile: qa-routine
                |
                `-- Ollama: gemma4:12b-it-q4_K_M
```

`qa-router-mcp` is a personal standalone repository. It is not part of the corporate `cdc-mcp` repository and does not import corporate credentials or packages.

## Components

### Codex Desktop

Codex owns task classification, evidence collection, corporate integrations, repository navigation, final validation, and the response shown to the user. A Codex routing skill describes when the local tools are appropriate, but the MCP server also enforces the same boundaries independently.

### qa-router-mcp

A small local Python STDIO MCP server managed with `uv`. It exposes narrow structured tools rather than a generic unrestricted chat or shell interface.

Initial tools:

1. `draft_test_cases` — produce a structured draft from a sanitized requirement and approved examples.
2. `summarize_logs` — group and summarize sanitized log fragments without diagnosing unsupported root causes.
3. `draft_automation_skeleton` — produce a non-writing automation-test skeleton from a supplied pattern and scenario.

Every result contains:

- `draft` — generated content;
- `assumptions` — assumptions made by the local model;
- `unverified` — items that require Codex verification;
- `learning_proposal` — optional reusable procedure or preference, never automatically persisted.

### Hermes Agent

Hermes runs under a dedicated `qa-routine` profile. It provides procedural skills and controlled cross-session memory. It receives no corporate MCP configuration and no general-purpose credential access.

### Ollama and Gemma

The initial model is `gemma4:12b-it-q4_K_M`. The operational context starts at 16K to preserve memory headroom for macOS, Codex, IDEs, browsers, Docker, and mobile tooling. A benchmark gate may raise the context to 32K later.

## Data handling

### Allowed transient input

- A minimal requirement fragment needed for the requested draft.
- Small selected code examples supplied by Codex.
- Sanitized log excerpts.
- Existing case structures with project identifiers and sensitive values removed.
- Generic domain terminology required to understand the scenario.

Transient input is used for the current inference and is not promoted to persistent memory.

### Allowed persistent memory

- Preferred test-case structure and writing style.
- Generic QA checklists and review procedures.
- Approved conventions for naming and formatting.
- Reusable lessons that contain no corporate identifiers, source code, URLs, credentials, incidents, user data, or business records.

### Forbidden persistent memory

- Jira and TestRail contents or identifiers.
- Source code, diffs, repository paths, branch names, and commit hashes.
- Logs, stack traces, environment URLs, infrastructure names, and incident details.
- Credentials, cookies, tokens, personal data, payment data, or test accounts.
- Product-specific facts that can become stale.

## Memory approval flow

1. Hermes returns an optional `learning_proposal` in a structured response.
2. The router validates it against forbidden-content rules and stores it in a local pending queue.
3. Codex shows the proposal to the user when it is materially useful.
4. Only explicit user approval moves the proposal into an approved skill or preference file.
5. Approved entries remain editable and removable, with no silent self-modification.

The first version will not implement autonomous skill rewriting.

## Routing policy

### Local delegation allowed

- Drafting test cases or checklists after Codex has selected the target behavior.
- Formatting, normalization, deduplication, and transformation of QA text.
- Grouping sanitized logs by visible signature.
- Generating test data that contains no real personal or credential data.
- Creating a draft automation skeleton from an explicitly supplied local pattern.
- Summarizing a bounded sanitized evidence packet.

### Codex-only work

- Jira-to-MR and requirements-to-diff analysis.
- CodeGraph navigation and blast-radius analysis.
- Choosing final coverage, severity, release readiness, or finding priority.
- Editing code and deciding whether tests pass.
- Cross-repository or shared-component analysis.
- Payments, balances, bonuses, KYC, AML, antifraud, security, migrations, and destructive operations.
- Every read or write involving corporate MCP servers.
- Final QA reports and all external-system writes.

### Fallback conditions

The router returns a structured refusal and Codex continues locally when:

- input violates the data policy;
- the task requests a forbidden decision or operation;
- Ollama or Hermes is unavailable;
- generation times out;
- output cannot satisfy the schema;
- the local model reports insufficient context or low confidence;
- the supplied packet exceeds the configured size limit.

## Security boundaries

- The MCP process uses an explicit allowlist of environment variables and receives no inherited credential variables where avoidable.
- The Hermes profile has no corporate MCP definitions.
- Version one has no shell-execution, filesystem-write, network-browsing, or external-publication tool exposed to Hermes.
- Router logs contain timings, tool names, decision reasons, and error categories, but not prompt bodies or generated corporate content.
- Repository writes remain a Codex-controlled operation under existing workspace approval rules.
- Configuration changes are backed up before modification and verified by read-back.

## Error handling

- Startup failure: Codex sees the MCP server as unavailable and continues without local delegation.
- Model timeout: the router terminates the request, reports a typed timeout, and does not retry indefinitely.
- Invalid structured output: one constrained repair attempt is allowed; failure returns control to Codex.
- Memory-policy violation: the proposal is rejected and recorded only as a policy event without the rejected content.
- Resource pressure: the model is unloaded after an idle interval; concurrent local generations are limited to one.

## Installation and configuration

Implementation will be staged:

1. Install and verify Ollama, then download the pinned Gemma model.
2. Benchmark 16K inference with normal desktop applications open.
3. Install Hermes and create the isolated `qa-routine` profile.
4. Implement and test `qa-router-mcp` with a fake model backend first, then Ollama/Hermes.
5. Add the local STDIO server and routing skill to Codex only after standalone tests pass.

No corporate MCP configuration will be copied into Hermes.

## Verification strategy

### Automated checks

- Unit tests for task-policy classification and refusal rules.
- Unit tests for sanitization and persistent-memory validation.
- Schema tests for all three MCP tools.
- Integration tests using a fake deterministic Hermes/Ollama backend.
- Local integration test against Gemma.
- MCP startup and tool-discovery smoke test from Codex.

### QA evaluation set

Use sanitized synthetic tasks representing:

- a TestRail-style case draft;
- a checklist transformation;
- duplicate-case detection;
- log signature grouping;
- a WDIO skeleton based on a supplied example;
- forbidden severity selection;
- forbidden corporate-memory proposal;
- local-backend outage and Codex fallback.

For each allowed task, compare the local draft with a Codex-reviewed expected structure. No production ticket or secret is needed for the initial evaluation.

### Performance gate

With typical work applications open:

- no sustained macOS memory-pressure warning;
- no material swap growth during a representative 16K request;
- one local request completes within an agreed interactive latency after measurement;
- model unload releases enough memory for Docker or mobile tooling.

The 32K context is enabled only if the 16K gate passes with comfortable headroom and a real task demonstrates the need.

## Rollout

The initial rollout is opt-in through explicit local MCP tools while Codex applies the routing instructions. After a small evaluation set is accepted, routine delegation becomes the default for allowed categories. A single configuration switch must disable all local delegation without affecting corporate MCP servers or ordinary Codex work.

## Expected outcome

The user keeps one Codex chat and existing QA workflows. Hermes and Gemma absorb repetitive drafting, while Codex preserves evidence quality, project awareness, safe tool access, and final responsibility.
