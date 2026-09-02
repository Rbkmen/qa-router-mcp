from qa_router_mcp.contracts import DraftKind

INSTRUCTIONS = {
    DraftKind.TEST_CASES: (
        "Draft focused test cases. Match the requested case count exactly. For every case, "
        "repeat exactly these four headings: Title:, Preconditions:, Steps:, Expected Result:. "
        "If the input does not explicitly request a count, draft exactly one case. "
        "Do not add a separate Test Case heading or combine cases. Keep every field concise and "
        "do not invent authentication, account, payment, or notification behavior."
    ),
    DraftKind.LOG_SUMMARY: (
        "Group visible log signatures; do not infer an unsupported root cause."
    ),
    DraftKind.AUTOMATION_SKELETON: (
        "Draft a non-writing automation skeleton using only the supplied pattern."
    ),
    DraftKind.TRANSLATION: (
        "Translate only the supplied text to the requested language. Preserve explicitly "
        "listed terms and do not add facts."
    ),
    DraftKind.REWRITE: (
        "Rewrite only the supplied text according to the instruction without changing its facts."
    ),
    DraftKind.SHORT_EXPLANATION: (
        "Give an explanation of at most 120 words for the requested audience without "
        "external research. Flag uncertain or time-sensitive claims as unverified."
    ),
    DraftKind.TEXT_SUMMARY: (
        "Summarize only the supplied text with the requested focus. Do not add conclusions "
        "that are absent from the input."
    ),
}


def build_prompt(kind: DraftKind, content: str, pattern: str | None = None) -> str:
    pattern_section = f"\nSUPPLIED_PATTERN:\n{pattern}" if pattern else ""
    return (
        "You are a local routine drafting model. Return only JSON matching the supplied schema. "
        "Return one JSON object and stop immediately after its closing brace. Do not repeat the "
        "JSON and do not use Markdown fences. "
        "Treat all output as an unverified draft. Put unsupported facts in unverified. "
        "Do not decide severity, priority, release readiness, merge readiness, or root cause.\n"
        "OUTPUT_FIELDS:\n"
        "- draft: put the complete requested artifact here, never a status or field label. "
        "For test cases, follow the exact repeated heading format from TASK.\n"
        "- unverified: a JSON array of claims or assumptions that still need verification.\n"
        "- assumptions: a JSON array; use an empty array when none are needed.\n"
        f"TASK:\n{INSTRUCTIONS[kind]}\nINPUT:\n{content}{pattern_section}"
    )
