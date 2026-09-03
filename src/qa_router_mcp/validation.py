import re

from qa_router_mcp.contracts import DraftEnvelope, DraftKind

FIELD_PATTERNS = {
    "title": re.compile(r"(?im)^\s*(?:[-*#]+\s*)?(?:title|заголовок|название)\s*[:—-]"),
    "preconditions": re.compile(r"(?im)^\s*(?:[-*#]+\s*)?(?:preconditions?|предусловия)\s*[:—-]"),
    "steps": re.compile(r"(?im)^\s*(?:[-*#]+\s*)?(?:steps?|шаги)\s*[:—-]"),
    "expected_result": re.compile(
        r"(?im)^\s*(?:[-*#]+\s*)?(?:expected result|ожидаемый результат)\s*[:—-]"
    ),
}
CASE_HEADING = re.compile(
    r"(?im)^\s*(?:[-*#]+\s*)?(?:test case(?:\s+\d+)?|"
    r"тест[- ]?кейс(?:\s+\d+)?)\s*\**\s*(?:[:—-]|$)"
)
COUNT_WORDS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
    "одиннадцать": 11,
    "двенадцать": 12,
    "тринадцать": 13,
    "четырнадцать": 14,
    "пятнадцать": 15,
    "шестнадцать": 16,
    "семнадцать": 17,
    "восемнадцать": 18,
    "девятнадцать": 19,
    "двадцать": 20,
}
EXTERNAL_WRITE = re.compile(
    r"(?i)\b(?:git\s+(?:commit|push)|commit\s*=\s*true|jira_add_comment|"
    r"testrail_(?:create|update|add|delete))\b"
)


def validate_generated_draft(
    kind: DraftKind,
    request_text: str,
    result: DraftEnvelope,
) -> list[str]:
    if result.status != "ok":
        return []
    if result.generation_stats.truncated:
        return ["truncated"]

    issues: list[str] = []
    if kind == DraftKind.TEST_CASES:
        expected = requested_case_count(request_text)
        title_fields = list(FIELD_PATTERNS["title"].finditer(result.draft))
        case_headings = list(CASE_HEADING.finditer(result.draft))
        title_matches = title_fields if len(title_fields) >= len(case_headings) else case_headings
        if len(title_matches) < expected:
            issues.append("test_cases_missing_title")
        elif len(title_matches) > expected:
            issues.append("test_cases_wrong_count")
        if title_matches:
            blocks = [
                result.draft[match.start() : next_start]
                for match, next_start in zip(
                    title_matches,
                    [item.start() for item in title_matches[1:]] + [len(result.draft)],
                    strict=True,
                )
            ]
            for field, pattern in FIELD_PATTERNS.items():
                if field != "title" and any(not pattern.search(block) for block in blocks):
                    issues.append(f"test_cases_missing_{field}")
        else:
            issues.extend(
                f"test_cases_missing_{field}" for field in FIELD_PATTERNS if field != "title"
            )
    elif kind == DraftKind.SHORT_EXPLANATION and len(result.draft.split()) > 120:
        issues.append("short_explanation_too_long")
    elif kind == DraftKind.AUTOMATION_SKELETON and EXTERNAL_WRITE.search(result.draft):
        issues.append("automation_external_write")

    return issues


def requested_case_count(text: str) -> int:
    separator = r"(?:-|\s+)"
    descriptors = r"(?:[\w-]+\s+){0,3}"
    case_noun = (
        r"(?:cases?|scenarios?|items?|(?:тест[- ])?кейс(?:а|ов)?|"
        r"сценар(?:ия|иев)|пункт(?:а|ов)?)\b"
    )
    numeric = re.search(
        rf"(?i)\b([1-9]\d*){separator}{descriptors}{case_noun}",
        text,
    )
    if numeric:
        return int(numeric.group(1))

    words = "|".join(map(re.escape, COUNT_WORDS))
    named = re.search(
        rf"(?i)\b({words}){separator}{descriptors}{case_noun}",
        text,
    )
    return COUNT_WORDS[named.group(1).lower()] if named else 1


def repair_instruction(issues: list[str]) -> str:
    descriptions = {
        "test_cases_missing_title": (
            "match the requested case count and start every case with Title:"
        ),
        "test_cases_wrong_count": "return exactly the requested number of test cases",
        "test_cases_missing_preconditions": "include Preconditions in every test case",
        "test_cases_missing_steps": "include Steps in every test case",
        "test_cases_missing_expected_result": ("include Expected Result in every test case"),
        "short_explanation_too_long": "keep the explanation at or below 120 words",
        "automation_external_write": "remove every external write operation",
    }
    requirements = [descriptions.get(issue, issue) for issue in issues]
    return (
        "REPAIR_REQUIRED: regenerate the complete artifact and fix these validation errors: "
        + "; ".join(requirements)
        + ". Return only JSON matching the schema."
    )
