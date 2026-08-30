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
        f"TASK:\n{INSTRUCTIONS[kind]}\nINPUT:\n{content}{pattern_section}"
    )
