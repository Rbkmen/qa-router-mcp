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
    QaTaskOutcome,
    QaTaskOutcomeReceipt,
    QaTaskType,
    TokenCount,
)
from qa_router_mcp.events import EventSink, JsonEventSink, valid_qa_task_metrics
from qa_router_mcp.policy import PolicyError, assert_allowed_request, sanitize_transient
from qa_router_mcp.prompts import build_prompt
from qa_router_mcp.quality import QualityGate, is_shadow_sample
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
        self._last_generation_finished: float | None = None

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

    def record_qa_task_outcome(
        self,
        *,
        task_type: QaTaskType,
        outcome: QaTaskOutcome,
        codegraph_calls: int,
        source_mcp_calls: int,
        qwen_used: bool,
        sol_used: bool,
        findings_identified: int,
        findings_confirmed: int,
        findings_rejected: int,
        qwen_edits: int,
        repeated_source_reads: int,
    ) -> QaTaskOutcomeReceipt:
        event = {
            "task_type": task_type,
            "outcome": outcome,
            "codegraph_calls": codegraph_calls,
            "source_mcp_calls": source_mcp_calls,
            "qwen_used": qwen_used,
            "sol_used": sol_used,
            "findings_identified": findings_identified,
            "findings_confirmed": findings_confirmed,
            "findings_rejected": findings_rejected,
            "qwen_edits": qwen_edits,
            "repeated_source_reads": repeated_source_reads,
        }
        if not valid_qa_task_metrics(event):
            raise ValueError("QA task metrics are inconsistent")
        return self.events.record_qa_task_outcome(event)

    def _record(
        self,
        kind: DraftKind,
        result: DraftEnvelope,
        started: float,
        input_chars: int,
        stats: GenerationStats | None = None,
        validation_repair: bool = False,
        estimated_prompt_tokens: int = 0,
        quality_gate: QualityGate | None = None,
        sensitive_category: str | None = None,
        tokenization_ms: float = 0,
        model_load_ms: float = 0,
        generation_ms: float = 0,
        validation_ms: float = 0,
        repair_ms: float = 0,
        cold_start_likely: bool = False,
    ) -> DraftEnvelope:
        gate = quality_gate or self.events.quality_gate(kind.value, self.settings.profile_version)
        sample_id = uuid4().hex
        interactive_ok = result.status == "ok" and self.settings.metrics_source == "interactive"
        shadow_required = interactive_ok and is_shadow_sample(sample_id)
        candidate_id = sample_id if interactive_ok and (gate.status == "canary" or shadow_required) else None
        result.quality_status = gate.status
        result.shadow_evaluation_required = shadow_required
        result.sensitive_category = sensitive_category
        result.tokenization_ms = round(tokenization_ms, 2)
        result.model_load_ms = round(model_load_ms, 2)
        result.generation_ms = round(generation_ms, 2)
        result.validation_ms = round(validation_ms, 2)
        result.repair_ms = round(repair_ms, 2)
        result.total_ms = round((monotonic() - started) * 1_000, 2)
        result.cold_start_likely = cold_start_likely
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
            quality_status=gate.status,
            shadow_evaluation_required=shadow_required,
            tokenization_ms=tokenization_ms,
            model_load_ms=model_load_ms,
            generation_ms=generation_ms,
            validation_ms=validation_ms,
            repair_ms=repair_ms,
            cold_start_likely=cold_start_likely,
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
        tokenization_ms = 0.0
        model_load_ms = 0.0
        generation_ms = 0.0
        validation_ms = 0.0
        repair_ms = 0.0
        validation_repair_attempted = False
        estimated_prompt_tokens = 0
        packet = content if pattern is None else f"{content}\n{pattern}"
        input_chars = len(packet)
        quality_gate = self.events.quality_gate(kind.value, self.settings.profile_version)
        if not self.settings.enabled:
            result = DraftEnvelope(status="fallback", reason="local_delegation_disabled")
            return self._record(kind, result, started, input_chars, quality_gate=quality_gate)
        if quality_gate.status == "paused":
            result = DraftEnvelope(status="fallback", reason="quality_gate_paused")
            return self._record(kind, result, started, input_chars, quality_gate=quality_gate)
        cold_start_likely = (
            self._last_generation_finished is None
            or monotonic() - self._last_generation_finished >= self.settings.ttl_seconds
        )
        try:
            assert_allowed_request(kind, packet)
            input_limit = self.settings.input_limit(kind)
            if input_chars > input_limit:
                raise PolicyError("input_too_large")
            safe_content = sanitize_transient(content, input_limit)
            safe_pattern = sanitize_transient(pattern, input_limit) if pattern else None
            prompt = build_prompt(kind, safe_content, safe_pattern)
            output_limit = self.settings.output_limit(kind, packet)
            phase_started = monotonic()
            token_count = await self.drafting.count_tokens(prompt)
            if isinstance(token_count, TokenCount):
                estimated_prompt_tokens = token_count.tokens
                model_load_ms = token_count.model_load_ms
                tokenization_ms = token_count.tokenization_ms
                cold_start_likely = token_count.cold_start
            else:
                estimated_prompt_tokens = token_count
                tokenization_ms = (monotonic() - phase_started) * 1_000
            if (
                estimated_prompt_tokens + output_limit + self.settings.context_reserve_tokens
                > self.settings.context
            ):
                raise PolicyError("token_budget_exceeded")
            phase_started = monotonic()
            result = await self.drafting.generate(
                prompt,
                max_output_tokens=output_limit,
            )
            generation_ms = (monotonic() - phase_started) * 1_000
            self._last_generation_finished = monotonic()
            phase_started = monotonic()
            issues = validate_generated_draft(kind, packet, result)
            validation_ms += (monotonic() - phase_started) * 1_000
            if issues == ["truncated"]:
                incomplete = DraftEnvelope(status="fallback", reason="local_model_truncated")
                return self._record(
                    kind,
                    incomplete,
                    started,
                    input_chars,
                    result.generation_stats,
                    estimated_prompt_tokens=estimated_prompt_tokens,
                    quality_gate=quality_gate,
                    tokenization_ms=tokenization_ms,
                    model_load_ms=model_load_ms,
                    generation_ms=generation_ms,
                    validation_ms=validation_ms,
                    cold_start_likely=cold_start_likely,
                )
            if issues:
                initial_stats = result.generation_stats
                validation_repair_attempted = True
                try:
                    phase_started = monotonic()
                    repaired = await self.drafting.generate(
                        f"{prompt}\n{repair_instruction(issues)}",
                        max_output_tokens=output_limit,
                        allow_schema_repair=False,
                    )
                    repair_ms = (monotonic() - phase_started) * 1_000
                    self._last_generation_finished = monotonic()
                except BackendError as exc:
                    raise BackendError(exc.code, initial_stats.merged(exc.stats)) from exc
                combined_stats = initial_stats.merged(repaired.generation_stats)
                repaired.set_generation_stats(combined_stats)
                phase_started = monotonic()
                remaining = validate_generated_draft(kind, packet, repaired)
                validation_ms += (monotonic() - phase_started) * 1_000
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
                        quality_gate,
                        tokenization_ms=tokenization_ms,
                        model_load_ms=model_load_ms,
                        generation_ms=generation_ms,
                        validation_ms=validation_ms,
                        repair_ms=repair_ms,
                        cold_start_likely=cold_start_likely,
                    )
                return self._record(
                    kind,
                    repaired,
                    started,
                    input_chars,
                    combined_stats,
                    True,
                    estimated_prompt_tokens,
                    quality_gate,
                    tokenization_ms=tokenization_ms,
                    model_load_ms=model_load_ms,
                    generation_ms=generation_ms,
                    validation_ms=validation_ms,
                    repair_ms=repair_ms,
                    cold_start_likely=cold_start_likely,
                )
            return self._record(
                kind,
                result,
                started,
                input_chars,
                estimated_prompt_tokens=estimated_prompt_tokens,
                quality_gate=quality_gate,
                tokenization_ms=tokenization_ms,
                model_load_ms=model_load_ms,
                generation_ms=generation_ms,
                validation_ms=validation_ms,
                cold_start_likely=cold_start_likely,
            )
        except PolicyError as exc:
            result = DraftEnvelope(status="refused", reason=exc.code)
            return self._record(
                kind,
                result,
                started,
                input_chars,
                estimated_prompt_tokens=estimated_prompt_tokens,
                quality_gate=quality_gate,
                sensitive_category=exc.category,
                tokenization_ms=tokenization_ms,
                model_load_ms=model_load_ms,
                generation_ms=generation_ms,
                validation_ms=validation_ms,
                repair_ms=repair_ms,
                cold_start_likely=cold_start_likely,
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
                quality_gate,
                tokenization_ms=tokenization_ms,
                model_load_ms=model_load_ms,
                generation_ms=generation_ms,
                validation_ms=validation_ms,
                repair_ms=repair_ms,
                cold_start_likely=cold_start_likely,
            )
