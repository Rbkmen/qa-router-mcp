from dataclasses import dataclass
from os import environ
from pathlib import Path

from qa_router_mcp.contracts import DraftKind

INPUT_CHAR_BUDGETS = {
    DraftKind.TEST_CASES: 20_000,
    DraftKind.LOG_SUMMARY: 40_000,
    DraftKind.AUTOMATION_SKELETON: 20_000,
    DraftKind.TRANSLATION: 12_000,
    DraftKind.REWRITE: 12_000,
    DraftKind.SHORT_EXPLANATION: 6_000,
    DraftKind.TEXT_SUMMARY: 24_000,
}

OUTPUT_TOKEN_BUDGETS = {
    DraftKind.TEST_CASES: 2_048,
    DraftKind.LOG_SUMMARY: 1_024,
    DraftKind.AUTOMATION_SKELETON: 2_048,
    DraftKind.TRANSLATION: 1_024,
    DraftKind.REWRITE: 1_024,
    DraftKind.SHORT_EXPLANATION: 384,
    DraftKind.TEXT_SUMMARY: 1_024,
}

PINNED_MODELS = {
    "qwen/qwen3.5-9b",
    "google/gemma-4-12b",
}


@dataclass(frozen=True, slots=True)
class Settings:
    enabled: bool = True
    model: str = "qwen/qwen3.5-9b"
    lmstudio_url: str = "http://127.0.0.1:1234"
    context: int = 16_384
    max_output_tokens: int = 2_048
    max_input_chars: int = 40_000
    timeout_seconds: float = 90.0
    max_parallel: int = 1
    ttl_seconds: int = 300
    data_dir: Path = Path("/Users/andreiviarshko/.qa-router")

    def input_limit(self, kind: DraftKind) -> int:
        return min(self.max_input_chars, INPUT_CHAR_BUDGETS[kind])

    def output_limit(self, kind: DraftKind) -> int:
        return min(self.max_output_tokens, OUTPUT_TOKEN_BUDGETS[kind])

    @property
    def metrics_path(self) -> Path:
        return self.data_dir / "metrics.jsonl"

    def __post_init__(self) -> None:
        if self.model not in PINNED_MODELS:
            raise ValueError("model must match a pinned model in the local MLX catalog")
        if self.context != 16_384 or self.max_parallel != 1:
            raise ValueError("context and parallelism must match the verified profile")
        if not self.lmstudio_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("LM Studio URL must use loopback")
        if self.ttl_seconds < 0:
            raise ValueError("TTL must be non-negative")

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        data_dir = Path(environ.get("QA_ROUTER_DATA_DIR", str(defaults.data_dir)))
        return cls(
            enabled=(
                environ.get("QA_ROUTER_ENABLED", "1") == "1"
                and not (data_dir / "disabled").exists()
            ),
            model=environ.get("QA_ROUTER_MODEL", defaults.model),
            lmstudio_url=environ.get(
                "QA_ROUTER_LMSTUDIO_URL", defaults.lmstudio_url
            ),
            context=int(environ.get("QA_ROUTER_CONTEXT", str(defaults.context))),
            max_output_tokens=int(
                environ.get("QA_ROUTER_MAX_OUTPUT", str(defaults.max_output_tokens))
            ),
            max_input_chars=int(
                environ.get("QA_ROUTER_MAX_INPUT_CHARS", str(defaults.max_input_chars))
            ),
            timeout_seconds=float(
                environ.get("QA_ROUTER_TIMEOUT", str(defaults.timeout_seconds))
            ),
            max_parallel=1,
            ttl_seconds=int(
                environ.get("QA_ROUTER_TTL_SECONDS", str(defaults.ttl_seconds))
            ),
            data_dir=data_dir,
        )
