"""Tests for extracting the final answer from planning-style model output."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.llm_manager import extract_final_answer, trim_to_sentence  # noqa: E402


def test_extracts_last_draft_section():
    text = (
        "The user wants a summary of a Bible class lesson.\n\n"
        "Key points:\n- First point\n- Second point\n\n"
        'Draft: "Sample Speaker taught on the first point, '
        "explaining the teaching from Scripture and calling hearers to "
        'faithful obedience."'
    )

    result = extract_final_answer(text)

    assert result.startswith("Sample Speaker taught")
    assert "The user wants" not in result
    assert "Key points" not in result
    assert not result.endswith('"')


def test_drops_leading_planning_without_markers():
    text = (
        "The user wants a 1000 character description.\n\n"
        "I need to keep it one paragraph.\n\n"
        "Sample Speaker examined the first point and pressed hearers toward "
        "faithful, obedient application in the life of the church."
    )

    result = extract_final_answer(text)

    assert result.startswith("Sample Speaker")


def test_clean_text_unchanged():
    text = "A single, complete description of the sermon with no planning around it."

    assert extract_final_answer(text) == text


def test_empty_input():
    assert extract_final_answer("") == ""


def test_task_planning_dropped():
    text = (
        "The task: Write a single paragraph summarizing the sermon.\n\n"
        "Sample Speaker opened the first point, tracing the teaching through "
        "Scripture, and calling for faithful application."
    )

    assert extract_final_answer(text).startswith("Sample Speaker")


def test_trim_keeps_sentence_boundary():
    text = "First sentence here. Second sentence that is longer. Third repeat. Fourth repeat."

    result = trim_to_sentence(text, 60)

    assert len(result) <= 60
    assert result.endswith(".")


def test_trim_single_long_sentence_closed():
    result = trim_to_sentence("word " * 100, 50)

    assert len(result) <= 51
    assert result.endswith(".")


def test_trim_under_limit_unchanged():
    assert trim_to_sentence("Short text.", 100) == "Short text."


def test_trailing_planning_paragraphs_dropped():
    text = (
        'Draft: "Sample Speaker taught on the first point, '
        "explaining the teaching from Scripture and calling hearers to "
        'faithful obedience."\n\nParagraph: I\'ll estimate. Let me count words: roughly 220 words.'
    )

    result = extract_final_answer(text)

    assert result.startswith("Sample Speaker taught")
    assert "Let me count" not in result
    assert not result.endswith("words.")
