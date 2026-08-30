from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DraftKind(StrEnum):
    TEST_CASES = "test_cases"
    LOG_SUMMARY = "log_summary"
    AUTOMATION_SKELETON = "automation_skeleton"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"


class DraftEnvelope(BaseModel):
    status: Literal["ok", "refused", "fallback"] = "ok"
    draft: str = ""
    assumptions: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    learning_proposal: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "DraftEnvelope":
        if self.status == "ok" and (not self.draft.strip() or not self.unverified):
            raise ValueError("successful drafts require content and unverified items")
        if self.status != "ok" and not self.reason:
            raise ValueError("non-success results require a reason")
        return self


class LearningProposal(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=2_000)
    status: ProposalStatus = ProposalStatus.PENDING


class LearningEnvelope(BaseModel):
    status: Literal["approved", "fallback"]
    proposal: LearningProposal | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_learning_result(self) -> "LearningEnvelope":
        if self.status == "approved" and self.proposal is None:
            raise ValueError("approved result requires a proposal")
        if self.status == "fallback" and not self.reason:
            raise ValueError("fallback result requires a reason")
        return self
