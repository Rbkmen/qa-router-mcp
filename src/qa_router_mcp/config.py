from dataclasses import dataclass
from os import environ
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    enabled: bool = True
    model: str = "gemma4:12b-it-q4_K_M"
    ollama_url: str = "http://127.0.0.1:11434"
    context: int = 64_000
    max_output_tokens: int = 2_048
    max_input_chars: int = 40_000
    timeout_seconds: float = 45.0
    max_parallel: int = 1
    keep_alive: str = "5m"
    data_dir: Path = Path("/Users/andreiviarshko/.qa-router")
    hermes_command: Path = Path("/Users/andreiviarshko/.local/bin/qa-routine")

    def __post_init__(self) -> None:
        if self.model != "gemma4:12b-it-q4_K_M":
            raise ValueError("model must match the pinned model")
        if self.context != 64_000 or self.max_parallel != 1:
            raise ValueError("context and parallelism must match the verified profile")
        if not self.ollama_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise ValueError("Ollama URL must use loopback")

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
            ollama_url=environ.get("QA_ROUTER_OLLAMA_URL", defaults.ollama_url),
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
            keep_alive=environ.get("QA_ROUTER_KEEP_ALIVE", defaults.keep_alive),
            data_dir=data_dir,
            hermes_command=Path(
                environ.get("QA_ROUTER_HERMES", str(defaults.hermes_command))
            ),
        )
