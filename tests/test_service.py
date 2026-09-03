import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.events import JsonEventSink
from qa_router_mcp.service import RouterService


class DraftFake:
    def __init__(self, result, repaired=None, token_count=100):
        self.results = [result] if repaired is None else [result, repaired]
        self.prompts = []
        self.token_prompts = []
        self.output_limits = []
        self.token_count = token_count

    async def count_tokens(self, prompt):
        self.token_prompts.append(prompt)
        return self.token_count

    async def generate(self, prompt, *, max_output_tokens=None, allow_schema_repair=True):
        self.prompts.append(prompt)
        self.output_limits.append(max_output_tokens)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_draft_sanitizes_transient_identifiers(tmp_path):
    drafting = DraftFake(
        DraftEnvelope(
            draft=(
                "Title: Guest checkout\nPreconditions: Guest user\n"
                "Steps: 1. Submit checkout\nExpected Result: Checkout is submitted"
            ),
            unverified=["Expected result"],
        )
    )
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(
        DraftKind.TEST_CASES,
        "ABC-123 at https://stage.test",
    )

    assert result.status == "ok"
    assert "ABC-123" not in drafting.prompts[0]
    assert "[ISSUE]" in drafting.prompts[0]


@pytest.mark.asyncio
async def test_policy_failure_returns_refusal_without_backend_call(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TEST_CASES, "password=secret")

    assert result.status == "refused"
    assert result.reason == "secret_detected"
    assert drafting.prompts == []
    assert drafting.token_prompts == []


@pytest.mark.parametrize(
    "input_text",
    [
        "Draft 13 test cases",
        "Draft thirteen test cases",
        "Draft twenty test cases",
        "Составь тринадцать кейсов",
        "Составь двадцать кейсов",
    ],
)
@pytest.mark.asyncio
async def test_more_than_twelve_test_cases_are_refused_before_backend_call(tmp_path, input_text):
    drafting = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TEST_CASES, input_text)

    assert result.status == "refused"
    assert result.reason == "requested_case_count_too_large"
    assert drafting.token_prompts == []
    assert drafting.prompts == []


@pytest.mark.asyncio
async def test_combined_packet_limit_is_enforced_before_backend(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="unused", unverified=["unused"]))
    settings = Settings(data_dir=tmp_path, max_input_chars=10)
    service = RouterService(settings, drafting)

    result = await service.draft(DraftKind.AUTOMATION_SKELETON, "123456", "78901")

    assert result.status == "refused"
    assert result.reason == "input_too_large"
    assert drafting.prompts == []


@pytest.mark.asyncio
async def test_token_budget_is_enforced_before_backend(tmp_path):
    drafting = DraftFake(
        DraftEnvelope(draft="unused", unverified=["unused"]),
        token_count=14_992,
    )
    service = RouterService(
        Settings(data_dir=tmp_path),
        drafting,
        JsonEventSink(tmp_path / "metrics.jsonl"),
    )

    result = await service.draft(DraftKind.TEST_CASES, "A1b2" * 5_000)

    assert result.status == "refused"
    assert result.reason == "token_budget_exceeded"
    assert drafting.prompts == []

    event = (tmp_path / "metrics.jsonl").read_text()
    assert '"estimated_prompt_tokens"' in event
    assert '"context_tokens":16384' in event


@pytest.mark.asyncio
async def test_tokenizer_failure_falls_back_before_generation(tmp_path):
    class FailingTokenizerBackend(DraftFake):
        async def count_tokens(self, prompt):
            raise BackendError("local_tokenizer_error")

    drafting = FailingTokenizerBackend(DraftEnvelope(draft="unused", unverified=["unused"]))
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.LOG_SUMMARY, "Synthetic timeout")

    assert result.status == "fallback"
    assert result.reason == "local_tokenizer_error"
    assert drafting.prompts == []


@pytest.mark.asyncio
async def test_default_event_sink_writes_to_settings_metrics_path(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="Translated", unverified=[]))
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TRANSLATION, "Translate: hello")

    assert result.status == "ok"
    assert result.canary_feedback_required is True
    assert result.draft_id is not None
    event = (tmp_path / "metrics.jsonl").read_text()
    assert '"source":"interactive"' in event
    assert f'"draft_id":"{result.draft_id}"' in event


@pytest.mark.asyncio
async def test_benchmark_draft_does_not_request_canary_feedback(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="Translated", unverified=[]))
    settings = Settings(data_dir=tmp_path, metrics_source="benchmark")
    service = RouterService(settings, drafting)

    result = await service.draft(DraftKind.TRANSLATION, "Translate: hello")

    assert result.status == "ok"
    assert result.canary_feedback_required is False
    assert result.draft_id is None


@pytest.mark.asyncio
async def test_structured_qa_draft_may_have_no_unverified_claims(tmp_path):
    complete = DraftEnvelope(
        draft=(
            "Title: Case\nPreconditions: Ready\nSteps: 1. Act\nExpected Result: Expected behavior"
        ),
        unverified=[],
    )
    drafting = DraftFake(complete)
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TEST_CASES, "Guest checkout")

    assert result.status == "ok"
    assert result.unverified == []
    assert len(drafting.prompts) == 1


@pytest.mark.asyncio
async def test_malformed_test_cases_are_repaired_once(tmp_path):
    malformed = DraftEnvelope(draft="Title: Only one case", unverified=["Review"])
    repaired = DraftEnvelope(
        draft=(
            "Title: Case 1\nPreconditions: Ready\nSteps: 1. Act\nExpected Result: One\n\n"
            "Title: Case 2\nPreconditions: Ready\nSteps: 1. Act\nExpected Result: Two\n\n"
            "Title: Case 3\nPreconditions: Ready\nSteps: 1. Act\nExpected Result: Three"
        ),
        unverified=["Review"],
    )
    drafting = DraftFake(malformed, repaired)
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TEST_CASES, "Draft 3 test cases")

    assert result.status == "ok"
    assert len(drafting.prompts) == 2
    assert "REPAIR_REQUIRED" in drafting.prompts[1]


@pytest.mark.asyncio
async def test_malformed_test_cases_fall_back_after_one_repair(tmp_path):
    malformed = DraftEnvelope(draft="Title: Only one case", unverified=["Review"])
    drafting = DraftFake(malformed, malformed)
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TEST_CASES, "Draft 3 test cases")

    assert result.status == "fallback"
    assert result.reason == "local_model_invalid_draft"
    assert len(drafting.prompts) == 2


@pytest.mark.asyncio
async def test_failed_semantic_repair_is_counted_in_metrics(tmp_path):
    malformed = DraftEnvelope(draft="Title: Only one case", unverified=["Review"])

    class FailingRepairBackend(DraftFake):
        async def generate(self, prompt, *, max_output_tokens=None, allow_schema_repair=True):
            self.prompts.append(prompt)
            if len(self.prompts) == 2:
                raise BackendError("local_model_invalid_response")
            return malformed

    path = tmp_path / "metrics.jsonl"
    service = RouterService(
        Settings(data_dir=tmp_path),
        FailingRepairBackend(malformed),
        JsonEventSink(path),
    )

    result = await service.draft(DraftKind.TEST_CASES, "Draft 3 test cases")

    assert result.status == "fallback"
    assert '"validation_repair":true' in path.read_text()


@pytest.mark.asyncio
async def test_truncated_draft_falls_back_without_repair(tmp_path):
    from qa_router_mcp.contracts import GenerationStats

    truncated = DraftEnvelope(draft="Translated", unverified=[])
    truncated.set_generation_stats(GenerationStats(requests=1, truncated=True))
    drafting = DraftFake(truncated)
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TRANSLATION, "Translate this")

    assert result.status == "fallback"
    assert result.reason == "local_model_truncated"
    assert len(drafting.prompts) == 1


@pytest.mark.asyncio
async def test_service_applies_per_tool_output_budget(tmp_path):
    drafting = DraftFake(DraftEnvelope(draft="Short explanation", unverified=[]))
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.SHORT_EXPLANATION, "Explain retries")

    assert result.status == "ok"
    assert drafting.output_limits == [512]


@pytest.mark.asyncio
async def test_routine_text_draft_without_unverified_succeeds(tmp_path):
    routine = DraftEnvelope(draft="Translated text", unverified=[])
    drafting = DraftFake(routine)
    service = RouterService(Settings(data_dir=tmp_path), drafting)

    result = await service.draft(DraftKind.TRANSLATION, "Translate this")

    assert result.status == "ok"
    assert result.unverified == []


def test_event_sink_never_logs_content(capsys):
    JsonEventSink().emit("draft_test_cases", "refused", 1.25, "secret_detected")

    event = capsys.readouterr().err
    assert "draft_test_cases" in event
    assert "secret_detected" in event
    assert "password=secret" not in event


def test_event_sink_logs_usage_without_content(capsys, tmp_path):
    from qa_router_mcp.contracts import GenerationStats

    path = tmp_path / "metrics.jsonl"
    JsonEventSink(path).emit(
        "translate_text",
        "ok",
        2.5,
        None,
        input_chars=50,
        stats=GenerationStats(prompt_tokens=20, output_tokens=10, requests=1),
        model="qwen/qwen3.5-9b",
        profile_version="router-v2",
        source="benchmark",
        estimated_prompt_tokens=42,
        context_tokens=16_384,
    )

    event = __import__("json").loads(path.read_text())
    assert event["schema_version"] == 2
    assert event["model"] == "qwen/qwen3.5-9b"
    assert event["profile_version"] == "router-v2"
    assert event["source"] == "benchmark"
    assert event["estimated_prompt_tokens"] == 42
    assert event["context_tokens"] == 16_384
    assert event["prompt_tokens"] == 20
    assert event["output_tokens"] == 10
    assert event["input_chars"] == 50
    assert "Translated text" not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600


def test_event_sink_records_content_free_canary_feedback(tmp_path):
    path = tmp_path / "metrics.jsonl"
    sink = JsonEventSink(path)
    draft_id = "a" * 32
    sink.emit(
        "test_cases",
        "ok",
        1.0,
        None,
        profile_version="router-v7",
        source="interactive",
        draft_id=draft_id,
    )

    receipt = sink.record_feedback(
        draft_id,
        "edited",
        "coverage",
    )

    events = [__import__("json").loads(line) for line in path.read_text().splitlines()]
    event = events[-1]
    assert receipt.status == "recorded"
    assert receipt.feedback_count == 1
    assert receipt.target == 50
    assert event == {
        "schema_version": 4,
        "event_type": "canary_feedback",
        "timestamp": event["timestamp"],
        "tool": "test_cases",
        "draft_id": draft_id,
        "profile_version": "router-v7",
        "source": "interactive",
        "verdict": "edited",
        "reason": "coverage",
    }
    assert "draft" not in event
    assert "content" not in event


def test_canary_uses_global_tool_quotas_across_sink_instances(tmp_path):
    path = tmp_path / "metrics.jsonl"
    sinks = [JsonEventSink(path) for _ in range(3)]
    draft_ids = [str(index) * 32 for index in range(1, 4)]
    issued_ids = []
    for sink, draft_id in zip(sinks, draft_ids, strict=True):
        issued_ids.append(
            sink.emit(
                "translation",
                "ok",
                1.0,
                None,
                profile_version="router-v7",
                source="interactive",
                draft_id=draft_id,
            )
        )

    assert issued_ids == [draft_ids[0], draft_ids[1], None]
    first = sinks[0].record_feedback(draft_ids[0], "accepted", "none")
    second = sinks[1].record_feedback(draft_ids[1], "accepted", "none")

    assert first.status == "recorded"
    assert second.status == "recorded"
    assert sinks[2].canary_active("translation") is False
    assert sinks[2].canary_active("test_cases") is True


def test_canary_accepts_only_one_feedback_for_an_issued_draft(tmp_path):
    path = tmp_path / "metrics.jsonl"
    sink = JsonEventSink(path)
    draft_id = "a" * 32
    sink.emit(
        "test_cases",
        "ok",
        1.0,
        None,
        profile_version="router-v7",
        source="interactive",
        draft_id=draft_id,
    )

    recorded = sink.record_feedback(draft_id, "accepted", "none")
    duplicate = sink.record_feedback(draft_id, "accepted", "none")
    unknown = sink.record_feedback("f" * 32, "accepted", "none")

    assert recorded.status == "recorded"
    assert duplicate.status == "duplicate"
    assert unknown.status == "not_found"
    assert unknown.feedback_count == 1


def test_canary_completes_only_after_every_tool_quota(tmp_path):
    from qa_router_mcp.events import CANARY_TOOL_TARGETS

    path = tmp_path / "metrics.jsonl"
    sink = JsonEventSink(path)
    index = 0
    for tool, target in CANARY_TOOL_TARGETS.items():
        for _ in range(target):
            index += 1
            draft_id = f"{index:032x}"
            sink.emit(
                tool,
                "ok",
                1.0,
                None,
                profile_version="router-v7",
                source="interactive",
                draft_id=draft_id,
            )
            receipt = sink.record_feedback(draft_id, "accepted", "none")

    assert receipt.status == "recorded"
    assert receipt.feedback_count == 50
    assert all(not sink.canary_active(tool) for tool in CANARY_TOOL_TARGETS)


def test_service_records_feedback_by_draft_id(tmp_path):
    service = RouterService(
        Settings(data_dir=tmp_path),
        DraftFake(DraftEnvelope(draft="unused", unverified=[])),
    )
    draft_id = "a" * 32
    service.events.emit(
        "test_cases",
        "ok",
        1.0,
        None,
        profile_version="router-v7",
        source="interactive",
        draft_id=draft_id,
    )

    receipt = service.record_canary_feedback(draft_id, "edited", "coverage")

    assert receipt.status == "recorded"


def test_malformed_feedback_does_not_consume_canary_quota(tmp_path):
    import json

    from qa_router_mcp.events import validated_canary_feedback

    path = tmp_path / "metrics.jsonl"
    sink = JsonEventSink(path)
    draft_id = "a" * 32
    sink.emit(
        "test_cases",
        "ok",
        1.0,
        None,
        profile_version="router-v7",
        source="interactive",
        draft_id=draft_id,
    )
    malformed = {
        "schema_version": 1,
        "event_type": "canary_feedback",
        "timestamp": "2026-09-03T00:00:00+00:00",
        "tool": "test_cases",
        "draft_id": draft_id,
        "profile_version": "router-v7",
        "source": "benchmark",
        "verdict": "bogus",
    }
    with path.open("a", encoding="utf-8") as metrics:
        metrics.write(json.dumps(malformed) + "\n")

    events = [json.loads(line) for line in path.read_text().splitlines()]

    assert validated_canary_feedback(events) == []
    assert sink.canary_active("test_cases") is True


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [("accepted", "coverage"), ("edited", "none"), ("rejected", "none")],
)
def test_canary_feedback_requires_a_consistent_reason(tmp_path, verdict, reason):
    service = RouterService(
        Settings(data_dir=tmp_path),
        DraftFake(DraftEnvelope(draft="unused", unverified=[])),
    )

    with pytest.raises(ValueError, match="feedback reason"):
        service.record_canary_feedback("a" * 32, verdict, reason)
