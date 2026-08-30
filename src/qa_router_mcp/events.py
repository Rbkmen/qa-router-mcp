import json
import sys
from typing import Protocol


class EventSink(Protocol):
    def emit(
        self,
        tool: str,
        outcome: str,
        duration_ms: float,
        error_category: str | None,
    ) -> None: ...


class JsonEventSink:
    def emit(
        self,
        tool: str,
        outcome: str,
        duration_ms: float,
        error_category: str | None,
    ) -> None:
        event = {
            "tool": tool,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 2),
            "error_category": error_category,
        }
        print(json.dumps(event, separators=(",", ":")), file=sys.stderr, flush=True)
