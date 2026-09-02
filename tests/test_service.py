import pytest

from qa_router_mcp.backends import BackendError
from qa_router_mcp.config import Settings
from qa_router_mcp.contracts import DraftEnvelope, DraftKind
from qa_router_mcp.events import JsonEventSink
from qa_router_mcp.service import RouterService


class DraftFake:
    def __init__(self, result, repaired=None):
        self.results = [result] if repaired is None else [result, repaired]
        self.prompts = []
        self.output_limits = []

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
async def test_structured_qa_draft_may_have_no_unverified_claims(tmp_path):
    complete = DraftEnvelope(
        draft=(
            "Title: Case\nPreconditions: Ready\nSteps: 1. Act\n"
            "Expected Result: Expected behavior"
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
    assert drafting.output_limits == [384]


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
    )

    event = path.read_text()
    assert '"prompt_tokens":20' in event
    assert '"output_tokens":10' in event
    assert '"input_chars":50' in event
    assert "Translated text" not in event
    assert path.stat().st_mode & 0o777 == 0o600
