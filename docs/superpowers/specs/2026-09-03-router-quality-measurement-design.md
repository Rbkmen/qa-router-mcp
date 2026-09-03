# QA Router Quality and Measurement Design

## Goal

Make local Qwen routing measurable and self-limiting without adding another model, agent, memory layer, or automatic cloud call.

## Design

1. Every generated event records separate model-loading, tokenization, generation, validation, repair, and total latency. LM Studio cold start is determined from its loaded-model list immediately before model acquisition; alternate test backends use a process-local idle-time heuristic.
2. Every tool has a quality state for the current profile: `active`, `canary`, or `paused`. The state uses the latest 20 validated, content-free reviews for that tool. With fewer than 10 reviews, conservative defaults apply. At 10 or more reviews, at least 80% acceptable drafts activates the route; at least 20% serious factual or coverage corrections pauses it; everything else remains canary.
3. A paused route returns `quality_gate_paused` before tokenization or generation. Qwen is never allowed to decide its own quality state.
4. Successful interactive drafts are deterministically selected for a 10% shadow sample from their random `draft_id`. The router only returns `shadow_evaluation_required`; the host decides whether to create an independent baseline. The router never creates a hidden cloud request.
5. Test-case coverage items have stable host-supplied `coverage_id` values. Qwen must return every ID exactly once. Validation rejects missing, duplicated, or invented IDs and uses the existing one-repair limit.
6. Sensitive-input refusals expose only a coarse `sensitive_category`; matching content is never logged or returned.
7. Client rules require one content-free `record_qa_task_outcome` call when a QA task completes, stops partially, or is blocked. The report shows outcome coverage and the new quality/timing signals.

## Compatibility and safety

- Legacy string coverage maps remain accepted and receive deterministic `COV-01` style IDs at the MCP boundary.
- Existing metrics remain readable; new generation events use a newer schema version.
- The current 16K context, Qwen3.5-9B model, single parallel request, and 300-second TTL remain unchanged until measured data justifies another profile.
- All external writes and final QA judgment remain with the host agent.
