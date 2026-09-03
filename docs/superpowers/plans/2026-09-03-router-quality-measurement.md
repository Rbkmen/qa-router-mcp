# QA Router Quality and Measurement Implementation Plan

1. Add failing contract tests for coverage IDs, refusal category, quality state, shadow sampling, and phase timing.
2. Implement the smallest contract, policy, quality-gate, service, event, prompt, and validation changes that satisfy those tests.
3. Add failing report tests for phase latency, shadow samples, quality states, and QA outcome coverage; implement report aggregation.
4. Update the routing policy, all client guides/rules, Codex skill, and README so clients use coverage IDs, shadow flags, canary feedback, and exactly one QA task outcome event.
5. Run focused tests after each change, then the full test suite, Ruff, launcher smoke test, and a live report read.
6. Review the final diff for scope, secrets, personal paths, obsolete Gemma/Hermes/OmniRoute references, then commit and push `main`.
