import pytest

from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.policy import (
    PolicyError,
    assert_allowed_request,
    sanitize_transient,
)


def test_transient_identifiers_are_replaced():
    raw = "ABC-123 at https://stage.example.test by qa@example.test commit deadbee"

    assert sanitize_transient(raw, 1_000) == (
        "[ISSUE] at [URL] by [EMAIL] commit [COMMIT]"
    )


def test_branch_and_repository_paths_are_replaced():
    raw = "Use feature/login-rework and src/project/private.py"

    assert sanitize_transient(raw, 1_000) == "Use [BRANCH] and [PATH]"


@pytest.mark.parametrize(
    "raw",
    ["Authorization: Bearer secret-value", "password=hunter2", "api_key: abc123"],
)
def test_secret_like_input_is_rejected(raw):
    with pytest.raises(PolicyError, match="secret_detected"):
        sanitize_transient(raw, 1_000)


def test_oversized_input_is_rejected():
    with pytest.raises(PolicyError, match="input_too_large"):
        sanitize_transient("x" * 11, 10)


def test_decision_request_is_refused():
    with pytest.raises(PolicyError, match="codex_only_decision"):
        assert_allowed_request(DraftKind.TEST_CASES, "Determine release readiness")
