import re

from qa_router_mcp.contracts import DraftKind
from qa_router_mcp.validation import requested_case_count


class PolicyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer|password|api[_-]?key|access[_-]?token|cookie)"
    r"\s*[:=]?\s*\S+"
)
DECISION = re.compile(
    r"(?i)\b(decide|determine|choose|assess)\b.{0,32}"
    r"\b(severity|priority|release readiness|merge readiness|root cause)\b"
)
SENSITIVE_FIELD = re.compile(
    r"(?ix)(?<!\w)[\"']?"
    r"(?:player[_-]?id|user[_-]?id|customer[_-]?id|account[_-]?id|session[_-]?id|"
    r"client[_-]?ip|ip[_-]?address|phone|card[_-]?number|pan|iban)"
    r"[\"']?\s*[:=]\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s,}]+)"
)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
UUID = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b"
)
SAFE_PLACEHOLDERS = {"", "null", "none", "nil", "redacted", "masked"}
REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"https?://[^\s]+"), "[URL]"),
    (re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b"), "[ISSUE]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (
        re.compile(r"(?<![0-9a-f])\b[0-9a-f]{7,40}\b(?![0-9a-f])", re.IGNORECASE),
        "[COMMIT]",
    ),
    (re.compile(r"/(?:Users|home|var|opt)/[^\s]+"), "[PATH]"),
    (
        re.compile(r"\b(?:feature|bugfix|hotfix|release)/[\w.-]+\b", re.IGNORECASE),
        "[BRANCH]",
    ),
    (re.compile(r"\b(?:src|tests?|packages?|apps?|lib)/[\w./-]+\b", re.IGNORECASE), "[PATH]"),
)
MAX_LOCAL_TEST_CASES = 12


def sanitize_transient(text: str, limit: int) -> str:
    if len(text) > limit:
        raise PolicyError("input_too_large")
    if SECRET.search(text):
        raise PolicyError("secret_detected")
    clean = text
    for pattern, replacement in REPLACEMENTS:
        clean = pattern.sub(replacement, clean)
    return clean.strip()


def assert_allowed_request(kind: DraftKind, text: str) -> None:
    if _contains_sensitive_data(text):
        raise PolicyError("sensitive_data_detected")
    if DECISION.search(text):
        raise PolicyError("codex_only_decision")
    if kind == DraftKind.TEST_CASES and requested_case_count(text) > MAX_LOCAL_TEST_CASES:
        raise PolicyError("requested_case_count_too_large")


def _contains_sensitive_data(text: str) -> bool:
    for match in SENSITIVE_FIELD.finditer(text):
        value = match.group("value").strip("\"'").strip()
        normalized = value.strip("[]").lower()
        if normalized not in SAFE_PLACEHOLDERS and set(value) != {"*"}:
            return True
    return IPV4.search(text) is not None or UUID.search(text) is not None
