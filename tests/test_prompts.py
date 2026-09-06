from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.prompts import build_prompt


def test_test_case_prompt_requires_one_canonical_block_per_case():
    prompt = build_prompt(DraftKind.TEST_CASES, "Draft two test cases")

    assert "Match the requested case count exactly" in prompt
    assert "Title:" in prompt
    assert "Preconditions:" in prompt
    assert "Steps:" in prompt
    assert "Expected Result:" in prompt
    assert (
        "Do not invent UI messages, field names, endpoints, test data, or preconditions" in prompt
    )


def test_test_case_prompt_builds_mandatory_skeleton_from_coverage_ids():
    prompt = build_prompt(
        DraftKind.TEST_CASES,
        "APPROVED_COVERAGE_MAP:\nCoverage ID: COV-A\nCoverage ID: COV-B",
    )

    assert "MANDATORY_DRAFT_SKELETON:" in prompt
    assert prompt.count("Coverage ID: COV-A") == 2
    assert prompt.count("Coverage ID: COV-B") == 2
    assert prompt.count("Title: <fill>") == 2


def test_translation_prompt_requires_verbatim_preserved_terms():
    prompt = build_prompt(DraftKind.TRANSLATION, "PRESERVE_TERMS: checkout\nTEXT: Checkout")

    assert "must appear verbatim" in prompt
