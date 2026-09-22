from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

import src.llm_manager as llm_manager_module
from src.auto_edit import (
    EditPlan,
    _resolve_transcript_char_budget,
    build_detection_prompt,
    detect_cut_points,
    render_review_snippets,
    validate_plan,
)
from src.llm_manager import LLMManager

CANNED_JSON = json.dumps(
    {
        "start": 245.0,
        "end": 3612.0,
        "confidence": 0.87,
        "evidence": "[04:05-04:11] In Him we live and move",
        "qa_judgment": "cut",
        "reasoning": "teaching starts after welcome; Q&A at 60:14",
    }
)

SEGMENTS: list[dict[str, Any]] = [
    {"start": 0.0, "end": 10.0, "text": "Welcome everyone, let us pray."},
    {"start": 245.0, "end": 255.0, "text": "In Him we live and move."},
    {"start": 3620.0, "end": 3630.0, "text": "Are there any questions before we finish?"},
]

CONFIG = {"auto_edit": {"qa_margin_seconds": 3.0, "min_sermon_seconds": 600}}


class FakeLLMManager:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, str]], operation: str = "", sermon_id=None) -> str:
        self.calls.append({"messages": messages, "operation": operation})
        return self.response


class SequenceLLMManager:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, str]], operation: str = "", sermon_id=None) -> str:
        self.calls.append({"messages": messages, "operation": operation})
        if not self.responses:
            raise AssertionError("chat called more times than scripted")
        return self.responses.pop(0)


class TestBuildDetectionPrompt:
    def test_contains_policy_markers(self):
        prompt = build_detection_prompt(SEGMENTS)
        for marker in ("qa_judgment", "teaching_continues", "evidence", "confidence"):
            assert marker in prompt

    def test_qa_margin_encoded(self):
        prompt = build_detection_prompt(SEGMENTS, qa_margin_seconds=5.0)
        assert "5" in prompt

    def test_segments_rendered_as_lines(self):
        prompt = build_detection_prompt(SEGMENTS)
        assert "[00:00-00:10] Welcome everyone, let us pray." in prompt

    def test_refinement_context_encoded(self):
        prompt = build_detection_prompt(
            SEGMENTS,
            previous_plan={"start": 10.0, "end": 200.0, "evidence": "old quote"},
            rejection_notes="Keep only the second class",
        )
        assert "RE-DETECTION" in prompt
        assert "Keep only the second class" in prompt
        assert "old quote" in prompt
        assert "Do not reuse the previous evidence" in prompt

    def test_no_refinement_markers_without_context(self):
        prompt = build_detection_prompt(SEGMENTS)
        assert "RE-DETECTION" not in prompt


class TestDetectCutPoints:
    def test_canned_json_parses(self):
        manager = FakeLLMManager(CANNED_JSON)
        plan = detect_cut_points(
            SEGMENTS, manager, CONFIG, duration=3700.0
        )
        assert plan.start == 245.0
        assert plan.end == 3612.0
        assert plan.confidence == pytest.approx(0.87)
        assert plan.needs_review is False
        assert plan.qa_judgment == "cut"
        assert "In Him we live" in plan.evidence
        assert manager.calls[0]["operation"] == "auto_edit"

    def test_markdown_fenced_json_parses(self):
        manager = FakeLLMManager(f"I will respond now.\n```json\n{CANNED_JSON}\n```")
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 245.0
        assert plan.needs_review is False

    def test_refinement_context_reaches_llm_prompt(self):
        manager = FakeLLMManager(CANNED_JSON)
        plan = detect_cut_points(
            SEGMENTS,
            manager,
            CONFIG,
            duration=3700.0,
            previous_plan={"start": 0.0, "end": 100.0, "evidence": "fallback"},
            rejection_notes="Only the second class please",
        )
        assert plan.start == 245.0
        user_content = manager.calls[0]["messages"][1]["content"]
        assert "RE-DETECTION" in user_content
        assert "Only the second class please" in user_content
        assert "fallback" in user_content

    def test_malformed_json_is_unavailable(self):
        manager = FakeLLMManager("sorry, I cannot answer that in JSON")
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 0.0
        assert plan.end == 0.0
        assert plan.needs_review is True
        assert plan.confidence == 0.0
        assert plan.detection_status == "unavailable"

    def test_out_of_range_values_are_unavailable(self):
        manager = FakeLLMManager(
            json.dumps(
                {
                    "start": 5000.0,
                    "end": 1000.0,
                    "confidence": 1.0,
                    "evidence": "x",
                    "qa_judgment": "cut",
                    "reasoning": "",
                }
            )
        )
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.needs_review is True
        assert plan.end == 0.0
        assert plan.detection_status == "unavailable"

    def test_end_clamped_to_duration(self):
        manager = FakeLLMManager(
            json.dumps(
                {
                    "start": 245.0,
                    "end": 3699.9,
                    "confidence": 0.9,
                    "evidence": "e",
                    "qa_judgment": "cut",
                    "reasoning": "",
                }
            )
        )
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3699.0)
        assert plan.end == 3699.0

    def test_sub_minimum_duration_marks_review(self):
        manager = FakeLLMManager(
            json.dumps(
                {
                    "start": 0.0,
                    "end": 120.0,
                    "confidence": 0.9,
                    "evidence": "e",
                    "qa_judgment": "cut",
                    "reasoning": "",
                }
            )
        )
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.needs_review is True

    def test_empty_segments_yields_unavailable_plan(self):
        manager = FakeLLMManager(CANNED_JSON)
        plan = detect_cut_points([], manager, CONFIG, duration=3600.0)
        assert plan.start == 0.0
        assert plan.end == 0.0
        assert plan.needs_review is True
        assert plan.detection_status == "unavailable"
        assert manager.calls == []

    def test_empty_segments_no_duration(self):
        plan = detect_cut_points([], FakeLLMManager(""), CONFIG, duration=None)
        assert plan.end == 0.0
        assert plan.needs_review is True
        assert plan.detection_status == "unavailable"

    def test_defaults_used_when_no_config(self):
        plan = detect_cut_points([], FakeLLMManager(""), None, duration=100.0)
        assert plan.needs_review is True
        assert plan.detection_status == "unavailable"


class TestDetectCutPointsRetries:
    def test_empty_then_valid_json_succeeds(self):
        manager = SequenceLLMManager(["", "   \n", CANNED_JSON])
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 245.0
        assert plan.end == 3612.0
        assert plan.needs_review is False
        assert len(manager.calls) == 3

    def test_garbage_then_valid_json_succeeds(self):
        manager = SequenceLLMManager(["", "sorry, no JSON here", CANNED_JSON])
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 245.0
        assert plan.needs_review is False
        assert len(manager.calls) == 3

    def test_exhausts_three_attempts_then_unavailable(self):
        manager = SequenceLLMManager(["", "garbage", "also garbage"])
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 0.0
        assert plan.end == 0.0
        assert plan.needs_review is True
        assert plan.confidence == 0.0
        assert plan.detection_status == "unavailable"
        assert len(manager.calls) == 3

    def test_sanity_check_failure_retried_and_exhausted(self):
        manager = SequenceLLMManager(
            [
                json.dumps(
                    {
                        "start": 5000.0,
                        "end": 1000.0,
                        "confidence": 1.0,
                        "evidence": "x",
                        "qa_judgment": "cut",
                        "reasoning": "",
                    }
                ),
                "",
                CANNED_JSON,
            ]
        )
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.start == 245.0
        assert plan.needs_review is False
        assert len(manager.calls) == 3


class TestDetectionFailureIsExplicit:
    def test_whitespace_only_responses_are_unavailable(self):
        manager = SequenceLLMManager(["", "   \n", "\t"])
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3308.3)
        assert plan.detection_status == "unavailable"
        assert plan.end == 0.0
        assert not (plan.start == 0.0 and plan.end == 3308.3)
        assert plan.needs_review is True
        assert len(manager.calls) == 3

    def test_timeout_is_unavailable_not_whole_file(self):
        class TimeoutManager:
            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages, operation="", sermon_id=None) -> str:
                self.calls += 1
                raise TimeoutError("auto_edit timed out after 120s")

        manager = TimeoutManager()
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3308.3)
        assert plan.detection_status == "unavailable"
        assert plan.end == 0.0
        assert manager.calls == 3
        assert "timed out" in plan.reasoning

    def test_unavailable_plan_renders_no_snippets(self, tmp_path):
        plan = EditPlan(start=0.0, end=0.0, detection_status="unavailable")
        snippets = render_review_snippets(
            tmp_path / "missing.mp4", plan, tmp_path / "snippets"
        )
        assert snippets == []
        assert not (tmp_path / "snippets").exists()

    def test_reasoning_wrapped_json_still_parses(self):
        wrapped = (
            'The requested shape is {"start": <seconds>, "end": <seconds>} '
            "but here is the answer:\n" + CANNED_JSON + "\nDone."
        )
        manager = FakeLLMManager(wrapped)
        plan = detect_cut_points(SEGMENTS, manager, CONFIG, duration=3700.0)
        assert plan.detection_status == "ok"
        assert plan.start == 245.0
        assert plan.end == 3612.0
        assert plan.needs_review is False


def _large_segments(count: int = 200) -> list[dict[str, Any]]:
    return [
        {"start": float(i), "end": float(i) + 1.0, "text": f"synthetic line {i} " + "x" * 40}
        for i in range(count)
    ]


class TestOversizedTranscript:
    def test_build_detection_prompt_elides_middle(self):
        prompt = build_detection_prompt(_large_segments(), max_transcript_chars=2000)
        assert "middle of the transcript elided" in prompt
        assert "synthetic line 0" in prompt
        assert "synthetic line 199" in prompt
        assert "synthetic line 100" not in prompt

    def test_detect_cut_points_bounds_the_prompt(self):
        manager = FakeLLMManager(CANNED_JSON)
        config = {
            "auto_edit": {
                "qa_margin_seconds": 3.0,
                "min_sermon_seconds": 0,
                "max_transcript_chars": 2000,
            }
        }
        plan = detect_cut_points(_large_segments(), manager, config, duration=3700.0)
        sent = manager.calls[0]["messages"][1]["content"]
        assert "middle of the transcript elided" in sent
        assert len(sent) < 4000
        assert plan.detection_status == "ok"

    def test_budget_follows_the_smallest_context(self):
        class Provider:
            def __init__(self, num_ctx: int) -> None:
                self.num_ctx = num_ctx

        class Manager:
            primary_provider = Provider(32768)
            fallback_providers = [Provider(8192)]
            validator_provider = None
            operation_providers: dict[str, Any] = {}

        budget = _resolve_transcript_char_budget({}, Manager())
        assert budget == int((8192 - 2048) * 3.5)

    def test_explicit_budget_wins(self):
        budget = _resolve_transcript_char_budget(
            {"auto_edit": {"max_transcript_chars": 12345}}, object()
        )
        assert budget == 12345


class TestValidatePlan:
    def test_valid_plan_has_no_problems(self):
        plan = EditPlan(start=0.0, end=3600.0)
        assert validate_plan(plan, 3600.0, 600.0) == []

    @pytest.mark.parametrize(
        "start,end,duration,needle",
        [
            (-1.0, 3600.0, 3600.0, "start is negative"),
            (0.0, 5000.0, 3600.0, "end exceeds video duration"),
            (3700.0, 5000.0, 3600.0, "start exceeds video duration"),
            (0.0, 300.0, 3600.0, "below minimum"),
            (100.0, 50.0, 3600.0, "end must be greater"),
        ],
    )
    def test_flagged_conditions(self, start, end, duration, needle):
        plan = EditPlan(start=start, end=end)
        problems = validate_plan(plan, duration, 600.0)
        assert any(needle in p for p in problems)

    def test_end_over_duration_tolerated_by_margin(self):
        plan = EditPlan(start=0.0, end=3600.5)
        assert validate_plan(plan, 3600.0, 600.0) == []


def _make_openai_stub() -> SimpleNamespace:
    return SimpleNamespace(OpenAI=lambda **kwargs: Mock())


CONFIG_WITH_OVERRIDE = {
    "llm": {
        "primary": {"enabled": False},
        "fallback": {"enabled": False},
        "operations": {
            "auto_edit": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": "https://schema.invalid/v1",
                "api_key": "test-key",
            }
        },
    }
}


class TestOperationProviderOverride:
    def test_operation_providers_populated(self, monkeypatch):
        monkeypatch.setattr(llm_manager_module, "openai", _make_openai_stub())
        manager = LLMManager(CONFIG_WITH_OVERRIDE)
        assert "auto_edit" in manager.operation_providers
        provider = manager.operation_providers["auto_edit"]
        assert provider.model == "gpt-4o-mini"
        assert provider.base_url == "https://schema.invalid/v1"

    def test_env_resolution(self, monkeypatch):
        monkeypatch.setattr(llm_manager_module, "openai", _make_openai_stub())
        monkeypatch.setenv("TEST_EDIT_KEY", "resolved-key")
        config: dict[str, Any] = {
            "llm": {
                "primary": {"enabled": False},
                "fallback": {"enabled": False},
                "operations": {
                    "auto_edit": {
                        "provider": "openai",
                        "model": "m",
                        "base_url": "${TEST_EDIT_BASE}",
                        "api_key": "$TEST_EDIT_KEY",
                    }
                },
            }
        }
        manager = LLMManager(config)
        provider = manager.operation_providers["auto_edit"]
        assert provider.api_key == "resolved-key"
        assert provider.base_url == "${TEST_EDIT_BASE}"

        monkeypatch.setenv("TEST_EDIT_BASE", "https://resolved.invalid/v1")
        config["llm"]["operations"]["auto_edit"]["base_url"] = "${TEST_EDIT_BASE}"
        manager = LLMManager(config)
        assert (
            manager.operation_providers["auto_edit"].base_url
            == "https://resolved.invalid/v1"
        )

    def test_chat_prefers_operation_provider_and_falls_back(self, monkeypatch):
        monkeypatch.setattr(llm_manager_module, "openai", _make_openai_stub())
        manager = LLMManager(CONFIG_WITH_OVERRIDE)
        provider = manager.operation_providers["auto_edit"]
        assert provider.model == "gpt-4o-mini"
        assert provider.base_url == "https://schema.invalid/v1"

        sentinel = "operation-provider-response"
        monkeypatch.setattr(
            type(manager.operation_providers["auto_edit"]), "chat", lambda self, m: sentinel
        )
        result = manager.chat([{"role": "user", "content": "hi"}], operation="auto_edit")
        assert result == sentinel

        monkeypatch.setattr(
            type(manager.operation_providers["auto_edit"]),
            "chat",
            Mock(side_effect=Exception("boom")),
        )
        monkeypatch.setattr(manager, "primary_provider", Mock())
        manager.primary_provider.chat = Mock(return_value="primary-response")
        fallback_provider = Mock()
        fallback_provider.chat = Mock(return_value="fallback-response")
        manager.fallback_providers = [fallback_provider]
        result = manager.chat([{"role": "user", "content": "hi"}], operation="auto_edit")
        assert result == "primary-response"

    def test_other_operations_unaffected(self, monkeypatch):
        monkeypatch.setattr(llm_manager_module, "openai", _make_openai_stub())
        manager = LLMManager(CONFIG_WITH_OVERRIDE)
        manager.primary_provider = None
        manager.fallback_providers = []
        with pytest.raises(Exception):  # noqa: B017
            manager.chat([{"role": "user", "content": "hi"}], operation="description")


class TestEditPlanDefaults:
    def test_defaults(self):
        plan = EditPlan()
        assert plan.fade_in == 1.0
        assert plan.logo_hold == 3.0
        assert plan.fade_to_black is True
        assert plan.confidence == 0.0
        assert plan.needs_review is True
        assert plan.qa_judgment == "cut"
