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
