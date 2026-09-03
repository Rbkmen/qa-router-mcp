import pytest

from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.policy import (
    PolicyError,
    assert_allowed_request,
    sanitize_transient,
)


def test_transient_identifiers_are_replaced():
    raw = "ABC-123 at https://stage.example.test by qa@example.test commit deadbee"

    assert sanitize_transient(raw, 1_000) == ("[ISSUE] at [URL] by [EMAIL] commit [COMMIT]")


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


@pytest.mark.parametrize(
    "raw",
    [
        "player_id=123456",
        "client_ip=10.20.30.40",
        "session_id=550e8400-e29b-41d4-a716-446655440000",
        "phone=+375291234567",
        "card_number=4111111111111111",
        "iban=GB82WEST12345698765432",
        '{"player_id":"123456"}',
        '{"session_id":"abc123"}',
        '{"phone":"+375291234567"}',
        '{"card_number":"4111111111111111"}',
        '{"iban":"GB82WEST12345698765432"}',
    ],
)
def test_sensitive_log_identifiers_are_rejected_before_local_routing(raw):
    with pytest.raises(PolicyError, match="sensitive_data_detected"):
        assert_allowed_request(DraftKind.LOG_SUMMARY, raw)


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("card_number=4111111111111111", "payment"),
        ("player_id=123456", "pii"),
        ("session_id=abc123", "identifier"),
        ("client_ip=10.20.30.40", "identifier"),
    ],
)
def test_sensitive_refusal_exposes_only_a_coarse_category(raw, category):
    with pytest.raises(PolicyError) as error:
        assert_allowed_request(DraftKind.LOG_SUMMARY, raw)

    assert error.value.category == category
    assert raw not in str(error.value)


@pytest.mark.parametrize(
    "raw",
    [
        "player_id=[REDACTED]",
        '{"session_id":"[MASKED]"}',
        "client_ip=***",
        "phone=null",
    ],
)
def test_redacted_sensitive_fields_are_allowed(raw):
    assert_allowed_request(DraftKind.LOG_SUMMARY, raw)
