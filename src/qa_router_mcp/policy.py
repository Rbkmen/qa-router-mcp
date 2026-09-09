import re

from qa_router_mcp.contracts import DraftKind, SensitiveCategory
from qa_router_mcp.validation import requested_case_count


class PolicyError(ValueError):
    def __init__(self, code: str, category: SensitiveCategory | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.category = category


SECRET = re.compile(
    r"(?ix)(?:"
    r"authorization[\"']?\s*[:=]\s*[\"']?bearer\s+[\"']?\S+|"
    r"\b(?:password|api[_\-\s]?key|access[_\-\s]?token|cookie|client[_\-\s]?secret|"
    r"refresh[_\-\s]?token|private[_\-\s]?key|secret[_\-\s]?key|session[_\-\s]?token|"
    r"id[_\-\s]?token|token|jwt)\b[\"']?\s*[:=]\s*(?:bearer\s+)?[\"']?\S+|"
    r"-----BEGIN(?:\s+[A-Z0-9]+)*\s+PRIVATE\s+KEY-----"
    r")"
)
DECISION = re.compile(
    r"(?ix)(?:"
    r"\b(?:decide|determine|choose|assess|identify|find|explain|analyze|give|tell|name|"
    r"state|show|describe|what\s+is)\b"
    r".{0,64}\b(?:severity|priority|release\s+readiness|merge\s+readiness|root\s+cause)\b|"
    r"\b(?:severity|priority|release\s+readiness|merge\s+readiness|root\s+cause)\b"
    r".{0,64}\b(?:decide|determine|choose|assess|identify|find|explain|analyze|give|tell|"
    r"name|state|show|describe)\b|"
    r"\b(?:why|почему)\b.{0,64}\b(?:fail\w*|error\w*|issue\w*|broken|wrong|timeout\w*|"
    r"причин\w*|ошиб\w*|сработ\w*|упал\w*)\b|"
    r"\b(?:определи|определить|найди|найти|укажи|указать|оцени|оценить|"
    r"выясни|выяснить|проанализируй|проанализировать|назови|назвать|сообщи|сообщить|"
    r"покажи|показать|объясни|объяснить)\b.{0,64}"
    r"\b(?:серьезност\w*|приоритет\w*|готовност\w*\s+к\s+(?:релизу|слиянию)|"
    r"корнев\w*\s+причин\w*|первопричин\w*)\b|"
    r"\b(?:серьезност\w*|приоритет\w*|готовност\w*\s+к\s+(?:релизу|слиянию)|"
    r"корнев\w*\s+причин\w*|первопричин\w*)\b.{0,64}"
    r"\b(?:определи|определить|найди|найти|укажи|указать|оцени|оценить|"
    r"выясни|выяснить|проанализируй|проанализировать|назови|назвать|сообщи|сообщить|"
    r"покажи|показать|объясни|объяснить)\b"
    r")"
)
SENSITIVE_FIELD = re.compile(
    r"(?ix)(?<!\w)[\"']?"
    r"(?P<field>player[_-]?id|user[_-]?id|customer[_-]?id|account[_-]?id|session[_-]?id|"
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
    (re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b", re.IGNORECASE), "[ISSUE]"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (
        re.compile(r"(?<![0-9a-f])\b[0-9a-f]{7,40}\b(?![0-9a-f])", re.IGNORECASE),
        "[COMMIT]",
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9])/(?:Users|home|var|opt|tmp|private|Applications|"
            r"Volumes|Library|System|etc|usr|bin|sbin|dev)/[^\s]+",
            re.IGNORECASE,
        ),
        "[PATH]",
    ),
    (
        re.compile(r"\b(?:feature|bugfix|hotfix|release)/[\w.-]+\b", re.IGNORECASE),
        "[BRANCH]",
    ),
    (re.compile(r"\b(?:src|tests?|packages?|apps?|lib)/[\w./-]+\b", re.IGNORECASE), "[PATH]"),
)
MAX_LOCAL_TEST_CASES = 12
STRUCTURAL_COVERAGE_LINE = re.compile(
    r"(?m)(^[ \t]*Coverage ID:[ \t]*COV-[A-Z0-9][A-Z0-9._-]{0,59}[ \t]*$)"
)


def sanitize_transient(text: str, limit: int, *, preserve_coverage_ids: bool = False) -> str:
    if len(text) > limit:
        raise PolicyError("input_too_large")
    if SECRET.search(text):
        raise PolicyError("secret_detected", "possible_secret")
    # Keep only typed structural ID lines; source text still receives every redaction.
    parts = STRUCTURAL_COVERAGE_LINE.split(text) if preserve_coverage_ids else [text]
    for index in range(0, len(parts), 2):
        for pattern, replacement in REPLACEMENTS:
            parts[index] = pattern.sub(replacement, parts[index])
    return "".join(parts).strip()


def assert_allowed_request(kind: DraftKind, text: str) -> None:
    sensitive_category = _sensitive_category(text)
    if sensitive_category is not None:
        raise PolicyError("sensitive_data_detected", sensitive_category)
    if DECISION.search(text):
        raise PolicyError("codex_only_decision")
    if kind == DraftKind.TEST_CASES and requested_case_count(text) > MAX_LOCAL_TEST_CASES:
        raise PolicyError("requested_case_count_too_large")


def _sensitive_category(text: str) -> SensitiveCategory | None:
    for match in SENSITIVE_FIELD.finditer(text):
        value = match.group("value").strip("\"'").strip()
        normalized = value.strip("[]").lower()
        if normalized not in SAFE_PLACEHOLDERS and set(value) != {"*"}:
            field = match.group("field").lower().replace("-", "_")
            if field in {"card_number", "pan", "iban"}:
                return "payment"
            if field in {"phone", "player_id", "user_id", "customer_id", "account_id"}:
                return "pii"
            return "identifier"
    if IPV4.search(text) is not None or UUID.search(text) is not None:
        return "identifier"
    return None
