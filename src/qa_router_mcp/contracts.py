from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

type CanaryVerdict = Literal["accepted", "edited", "rejected"]
type CanaryReason = Literal["none", "factual", "coverage", "format", "too_verbose", "other"]
type QaTaskType = Literal[
    "ordinary_review",
    "widget_review",
    "epic_analysis",
    "requirements_analysis",
    "qa_planning",
    "autotest_implementation",
    "other",
]
type QaTaskOutcome = Literal["completed", "partial", "blocked"]
type QualityStatus = Literal["active", "canary", "paused"]
type SensitiveCategory = Literal["possible_secret", "pii", "payment", "identifier"]


@dataclass(frozen=True, slots=True)
class GenerationStats:
    prompt_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    truncated: bool = False

    def merged(self, other: "GenerationStats") -> "GenerationStats":
        return GenerationStats(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            requests=self.requests + other.requests,
            truncated=self.truncated or other.truncated,
        )


@dataclass(frozen=True, slots=True)
class TokenCount:
    tokens: int
    model_load_ms: float
    tokenization_ms: float
    cold_start: bool


class DraftKind(StrEnum):
    TEST_CASES = "test_cases"
    LOG_SUMMARY = "log_summary"
    AUTOMATION_SKELETON = "automation_skeleton"
    TRANSLATION = "translation"
    REWRITE = "rewrite"
    SHORT_EXPLANATION = "short_explanation"
    TEXT_SUMMARY = "text_summary"


class DraftEnvelope(BaseModel):
    status: Literal["ok", "refused", "fallback"] = "ok"
    draft: str = ""
    assumptions: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    reason: str | None = None
    canary_feedback_required: bool = False
    draft_id: str | None = None
    quality_status: QualityStatus = "canary"
    shadow_evaluation_required: bool = False
    sensitive_category: SensitiveCategory | None = None
    tokenization_ms: float = 0
    model_load_ms: float = 0
    generation_ms: float = 0
    validation_ms: float = 0
    repair_ms: float = 0
    total_ms: float = 0
    cold_start_likely: bool = False
    _generation_stats: GenerationStats = PrivateAttr(default_factory=GenerationStats)

    @property
    def generation_stats(self) -> GenerationStats:
        return self._generation_stats

    def set_generation_stats(self, stats: GenerationStats) -> None:
        self._generation_stats = stats

    @model_validator(mode="after")
    def validate_status_payload(self) -> "DraftEnvelope":
        if self.status == "ok":
            if not self.draft.strip():
                raise ValueError("successful drafts require content")
            self.reason = None
        elif not self.reason:
            raise ValueError("non-success results require a reason")
        return self


class CoverageItem(BaseModel):
    coverage_id: str = Field(pattern=r"^COV-[A-Z0-9][A-Z0-9._-]{0,59}$")
    purpose: str = Field(min_length=1)
    source: str = Field(min_length=1)
    state: str = Field(min_length=1)
    expected_invariant: str = Field(min_length=1)


class CanaryFeedbackReceipt(BaseModel):
    status: Literal["recorded", "complete", "duplicate", "not_found", "unavailable", "invalid"]
    feedback_count: int
    target: int


class QaTaskOutcomeReceipt(BaseModel):
    status: Literal["recorded", "unavailable"]
