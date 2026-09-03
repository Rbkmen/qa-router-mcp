from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.validation import (
    repair_instruction,
    requested_case_count,
    validate_generated_draft,
)


def test_requested_case_count_supports_english_and_russian():
    assert requested_case_count("Draft three test cases") == 3
    assert requested_case_count("Сделай 4 кейса") == 4
    assert requested_case_count("Сделай три тест-кейса") == 3
    assert requested_case_count("Draft three focused smoke test cases") == 3
    assert requested_case_count("Draft 12 focused test cases") == 12
    assert requested_case_count("Draft a focused case") == 1


def test_short_explanation_over_120_words_is_rejected():
    result = DraftEnvelope(draft="word " * 121, unverified=[])

    assert validate_generated_draft(
        DraftKind.SHORT_EXPLANATION,
        "Explain retries",
        result,
    ) == ["short_explanation_too_long"]


def test_source_bound_log_summary_may_have_no_unverified_claims():
    result = DraftEnvelope(draft="Visible signatures: timeout (2)", unverified=[])

    assert (
        validate_generated_draft(
            DraftKind.LOG_SUMMARY,
            "ERROR timeout\nERROR timeout",
            result,
        )
        == []
    )


def test_numbered_test_case_heading_counts_as_title():
    result = DraftEnvelope(
        draft=(
            "Test Case 1: Saved card\nPreconditions: Ready\nSteps: 1. Act\n"
            "Expected Result: Success\n\n"
            "Test Case 2: New card\nPreconditions: Ready\nSteps: 1. Act\n"
            "Expected Result: Success"
        ),
        unverified=[],
    )

    assert (
        validate_generated_draft(
            DraftKind.TEST_CASES,
            "Draft two test cases",
            result,
        )
        == []
    )


def test_every_test_case_block_requires_all_fields():
    result = DraftEnvelope(
        draft=(
            "Title: Complete case\nPreconditions: First\nPreconditions: Duplicate\n"
            "Steps: 1. Act\nSteps: 2. Act\nExpected Result: First\n"
            "Expected Result: Duplicate\n\nTitle: Incomplete case"
        ),
        unverified=[],
    )

    assert validate_generated_draft(
        DraftKind.TEST_CASES,
        "Draft two test cases",
        result,
    ) == [
        "test_cases_missing_preconditions",
        "test_cases_missing_steps",
        "test_cases_missing_expected_result",
    ]


def test_numbered_heading_and_title_field_do_not_count_as_two_cases():
    result = DraftEnvelope(
        draft=(
            "Test Case 1: Checkout\n\nTitle: Valid guest checkout\n"
            "Preconditions: Ready\nSteps: 1. Submit\nExpected Result: Success"
        ),
        unverified=[],
    )

    assert validate_generated_draft(
        DraftKind.TEST_CASES,
        "Draft two test cases",
        result,
    ) == ["test_cases_missing_title"]


def test_extra_test_case_is_rejected():
    result = DraftEnvelope(
        draft="\n\n".join(
            f"Title: Case {number}\nPreconditions: Ready\nSteps: 1. Act\n"
            f"Expected Result: Result {number}"
            for number in range(1, 4)
        ),
        unverified=[],
    )

    assert validate_generated_draft(
        DraftKind.TEST_CASES,
        "Draft exactly 2 test cases",
        result,
    ) == ["test_cases_wrong_count"]


def test_markdown_test_case_heading_without_colon_counts_as_title():
    result = DraftEnvelope(
        draft=("## Test Case 1\nPreconditions: Ready\nSteps: 1. Act\nExpected Result: Success"),
        unverified=[],
    )

    assert validate_generated_draft(DraftKind.TEST_CASES, "Draft one case", result) == []


def test_repair_instruction_uses_actionable_language():
    instruction = repair_instruction(["test_cases_missing_steps"])

    assert "include Steps in every test case" in instruction
    assert "test_cases_missing_steps" not in instruction


def test_automation_skeleton_cannot_contain_external_write():
    result = DraftEnvelope(
        draft="Run checks and then git push origin branch",
        unverified=["Review"],
    )

    assert validate_generated_draft(
        DraftKind.AUTOMATION_SKELETON,
        "Draft a skeleton",
        result,
    ) == ["automation_external_write"]


def test_automation_skeleton_cannot_contain_git_commit():
    result = DraftEnvelope(
        draft="git commit -m 'generated change'",
        unverified=["Review"],
    )

    assert validate_generated_draft(
        DraftKind.AUTOMATION_SKELETON,
        "Draft a skeleton",
        result,
    ) == ["automation_external_write"]
