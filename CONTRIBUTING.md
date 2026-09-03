# Contributing to QA Router MCP

Thank you for helping improve QA Router MCP. Contributions should preserve its core goal:
provide bounded, privacy-aware local drafts while leaving evidence gathering, QA judgment,
code changes, and external-system writes under the host AI agent's control.

## Development setup

Requirements:

- macOS on Apple Silicon;
- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/);
- LM Studio with the `lms` CLI for opt-in live tests.

Clone the repository and install all dependencies:

```bash
git clone https://github.com/Rbkmen/qa-router-mcp.git
cd qa-router-mcp
uv sync
```

Run the required local checks:

```bash
uv run pytest -q
uv run ruff check .
```

The default test suite must not require LM Studio, a downloaded model, network access, or
credentials.

## Architecture guardrails

Changes must keep these boundaries intact:

- The host AI agent remains the primary orchestrator and final decision-maker.
- The local router produces drafts only; its output is never evidence or authorization.
- Only bounded, sanitized input may be sent to the local model.
- The LM Studio endpoint must remain loopback-only.
- Secrets, credentials, personal data, payment data, raw unrestricted logs, full repositories,
  and unrestricted corporate documents must never be routed locally.
- The router must not store prompts, generated content, conversation history, or persistent QA
  memory.
- Operational metrics must remain content-free.
- Policy, transport, context, truncation, schema, and semantic-validation failures must return
  control to the host agent.
- Complex read-only escalation belongs to the client and must not become a hidden server-side
  model call.

Proposals that change these boundaries should be discussed in a GitHub issue before
implementation.

## Making a change

Keep changes focused and follow the existing module boundaries. When adding or modifying an MCP
tool, review every affected layer:

1. Public contracts and limits in `contracts.py` and `config.py`.
2. MCP exposure and orchestration in `server.py` and `service.py`.
3. Routing policy, prompts, validation, and fallback behavior.
4. Content-free events, quality gates, and reporting when applicable.
5. Unit tests, routing policy, README, and client instructions.

Test-case drafting must preserve the exact one-to-one set of supplied stable `COV-*` coverage
IDs. Validation or repair changes must remain bounded and must not silently convert a failed
local draft into an accepted result.

## Testing

Every pull request should pass:

```bash
uv run pytest -q
uv run ruff check .
```

Add or update tests for observable behavior, boundary conditions, policy refusals, validation,
fallbacks, and content-free metrics. Do not weaken an existing assertion solely to make a new
implementation pass.

Live tests are opt-in and require the verified local model profile:

```bash
QA_ROUTER_LIVE=1 uv run pytest -q tests/test_live_lmstudio.py -s
QA_ROUTER_BENCHMARK=1 uv run pytest -q tests/test_live_benchmark.py -s
```

Do not include live-test output, local metrics, model files, credentials, or machine-specific
configuration in a commit.

## Documentation and client integrations

Update `docs/ROUTING_POLICY.md` when routing behavior or safety boundaries change. If a change
affects host behavior, update every relevant guide under `docs/clients/` and template under
`client-rules/`. Keep examples generic: do not include personal paths, account names, internal
URLs, issue data, or secrets.

Architecture diagrams must match the implemented and documented behavior. Avoid presenting an
optional client capability as a mandatory server dependency.

## Commits and pull requests

- Create a focused branch from the current default branch.
- Use a concise commit subject that describes the outcome; `feat:`, `fix:`, `docs:`, `test:`, and
  `refactor:` prefixes are welcome.
- Keep unrelated refactoring out of the same pull request.
- Explain the motivation, behavior change, safety impact, and verification performed.
- Call out anything that could not be verified.
- Include screenshots only when visual documentation changes.

Before requesting review, confirm that:

- [ ] tests and Ruff pass;
- [ ] new behavior has focused automated coverage;
- [ ] privacy and fallback boundaries remain intact;
- [ ] metrics contain no source or generated content;
- [ ] affected documentation and client rules are updated;
- [ ] the diff contains no generated, local, or sensitive files.
