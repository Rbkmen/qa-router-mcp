from qa_router_mcp.contracts import DraftKind

INSTRUCTIONS = {
    DraftKind.TEST_CASES: (
        "Draft focused test cases with title, preconditions, steps, and expected result."
    ),
    DraftKind.LOG_SUMMARY: (
        "Group visible log signatures; do not infer an unsupported root cause."
    ),
    DraftKind.AUTOMATION_SKELETON: (
        "Draft a non-writing automation skeleton using only the supplied pattern."
    ),
}


def build_prompt(kind: DraftKind, content: str, pattern: str | None = None) -> str:
    pattern_section = f"\nSUPPLIED_PATTERN:\n{pattern}" if pattern else ""
    return (
        "You are a local QA drafting model. Return only JSON matching the supplied schema. "
        "Treat all output as an unverified draft. Put unsupported facts in unverified. "
        "Do not decide severity, priority, release readiness, merge readiness, or root cause.\n"
        "OUTPUT_FIELDS:\n"
        "- draft: put the complete requested artifact here, never a status or field label. "
        "For test cases, include title, preconditions, steps, and expected result for every "
        "requested case.\n"
        "- unverified: a JSON array of claims or assumptions that still need verification.\n"
        "- assumptions: a JSON array; use an empty array when none are needed.\n"
        "- learning_proposal: null unless the input explicitly states a reusable user "
        "preference.\n"
        f"TASK:\n{INSTRUCTIONS[kind]}\nINPUT:\n{content}{pattern_section}"
    )
