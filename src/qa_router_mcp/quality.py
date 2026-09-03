from dataclasses import dataclass

DEFAULT_ACTIVE_TOOLS = {"translation", "rewrite", "text_summary", "short_explanation"}
SERIOUS_REASONS = {"factual", "coverage"}
MIN_REVIEWS = 10
WINDOW_SIZE = 20


@dataclass(frozen=True, slots=True)
class QualityGate:
    status: str
    reviews: int
    acceptable_rate: float | None
    serious_rate: float | None


def assess_quality(tool: str, feedback: list[dict[str, object]]) -> QualityGate:
    relevant = [event for event in feedback if event.get("tool") == tool][-WINDOW_SIZE:]
    reviews = len(relevant)
    if reviews < MIN_REVIEWS:
        default = "active" if tool in DEFAULT_ACTIVE_TOOLS else "canary"
        return QualityGate(default, reviews, None, None)

    serious = sum(event.get("reason") in SERIOUS_REASONS for event in relevant)
    acceptable = sum(
        event.get("verdict") == "accepted"
        or (event.get("verdict") == "edited" and event.get("reason") not in SERIOUS_REASONS)
        for event in relevant
    )
    acceptable_rate = round(acceptable / reviews, 3)
    serious_rate = round(serious / reviews, 3)
    if serious_rate >= 0.2:
        status = "paused"
    elif acceptable_rate >= 0.8:
        status = "active"
    else:
        status = "canary"
    return QualityGate(status, reviews, acceptable_rate, serious_rate)


def is_shadow_sample(sample_id: str) -> bool:
    return int(sample_id, 16) % 10 == 0
