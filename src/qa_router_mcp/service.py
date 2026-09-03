from time import monotonic
from uuid import uuid4

from qa_router_mcp.backends import BackendError, DraftBackend
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import (
    CanaryFeedbackReceipt,
    CanaryReason,
    CanaryVerdict,
    DraftEnvelope,
    DraftKind,
    GenerationStats,
)
from qa_router_mcp.events import EventSink, JsonEventSink
from qa_router_mcp.policy import PolicyError, assert_allowed_request, sanitize_transient
from qa_router_mcp.prompts import build_prompt
from qa_router_mcp.validation import repair_instruction, validate_generated_draft


class RouterService:
    def __init__(
        self,
        settings: Settings,
        drafting: DraftBackend,
        events: EventSink | None = None,
    ) -> None:
        self.settings = settings
        self.drafting = drafting
        self.events = events or JsonEventSink(settings.metrics_path)

    def record_canary_feedback(
        self,
        draft_id: str,
        verdict: CanaryVerdict,
        reason: CanaryReason,
    ) -> CanaryFeedbackReceipt:
        if (verdict == "accepted") != (reason == "none"):
            raise ValueError("feedback reason must be none only for accepted drafts")
        return self.events.record_feedback(
            draft_id,
            verdict,
            reason,
        )

    def _record(
        self,
        kind: DraftKind,
        result: DraftEnvelope,
        started: float,
        input_chars: int,
        stats: GenerationStats | None = None,
        validation_repair: bool = False,
        estimated_prompt_tokens: int = 0,
    ) -> DraftEnvelope:
        candidate_id = None
        if result.status == "ok" and self.settings.metrics_source == "interactive":
            candidate_id = uuid4().hex
        result.draft_id = self.events.emit(
            kind.value,
            result.status,
            (monotonic() - started) * 1_000,
            result.reason,
            input_chars,
            stats or result.generation_stats,
            validation_repair,
            model=self.settings.model,
            profile_version=self.settings.profile_version,
            source=self.settings.metrics_source,
            estimated_prompt_tokens=estimated_prompt_tokens,
            context_tokens=self.settings.context,
            draft_id=candidate_id,
        )
        result.canary_feedback_required = result.draft_id is not None
        return result

    async def draft(
        self,
        kind: DraftKind,
        content: str,
        pattern: str | None = None,
    ) -> DraftEnvelope:
        started = monotonic()
        validation_repair_attempted = False
        estimated_prompt_tokens = 0
        packet = content if pattern is None else f"{content}\n{pattern}"
        input_chars = len(packet)
        if not self.settings.enabled:
            result = DraftEnvelope(status="fallback", reason="local_delegation_disabled")
            return self._record(kind, result, started, input_chars)
        try:
            assert_allowed_request(kind, packet)
            input_limit = self.settings.input_limit(kind)
            if input_chars > input_limit:
                raise PolicyError("input_too_large")
            safe_content = sanitize_transient(content, input_limit)
            safe_pattern = sanitize_transient(pattern, input_limit) if pattern else None
            prompt = build_prompt(kind, safe_content, safe_pattern)
            output_limit = self.settings.output_limit(kind, packet)
            estimated_prompt_tokens = await self.drafting.count_tokens(prompt)
            if (
                estimated_prompt_tokens + output_limit + self.settings.context_reserve_tokens
                > self.settings.context
            ):
                raise PolicyError("token_budget_exceeded")
            result = await self.drafting.generate(
                prompt,
                max_output_tokens=output_limit,
            )
            issues = validate_generated_draft(kind, packet, result)
            if issues == ["truncated"]:
                incomplete = DraftEnvelope(status="fallback", reason="local_model_truncated")
                return self._record(
                    kind,
                    incomplete,
                    started,
                    input_chars,
                    result.generation_stats,
                    estimated_prompt_tokens=estimated_prompt_tokens,
                )
            if issues:
                initial_stats = result.generation_stats
                validation_repair_attempted = True
                try:
                    repaired = await self.drafting.generate(
                        f"{prompt}\n{repair_instruction(issues)}",
                        max_output_tokens=output_limit,
                        allow_schema_repair=False,
                    )
                except BackendError as exc:
                    raise BackendError(exc.code, initial_stats.merged(exc.stats)) from exc
                combined_stats = initial_stats.merged(repaired.generation_stats)
                repaired.set_generation_stats(combined_stats)
                remaining = validate_generated_draft(kind, packet, repaired)
                if remaining:
                    incomplete = DraftEnvelope(
                        status="fallback",
                        reason="local_model_invalid_draft",
                    )
                    return self._record(
                        kind,
                        incomplete,
                        started,
                        input_chars,
                        combined_stats,
                        True,
                        estimated_prompt_tokens,
                    )
                return self._record(
                    kind,
                    repaired,
                    started,
                    input_chars,
                    combined_stats,
                    True,
                    estimated_prompt_tokens,
                )
            return self._record(
                kind,
                result,
                started,
                input_chars,
                estimated_prompt_tokens=estimated_prompt_tokens,
            )
        except PolicyError as exc:
            result = DraftEnvelope(status="refused", reason=exc.code)
            return self._record(
                kind,
                result,
                started,
                input_chars,
                estimated_prompt_tokens=estimated_prompt_tokens,
            )
        except BackendError as exc:
            result = DraftEnvelope(status="fallback", reason=exc.code)
            return self._record(
                kind,
                result,
                started,
                input_chars,
                exc.stats,
                validation_repair_attempted,
                estimated_prompt_tokens,
            )
