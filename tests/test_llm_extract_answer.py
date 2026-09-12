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
        "Key points:\n- Third petition\n- Will of decree vs precept\n\n"
        'Draft: "Sample Speaker taught on the third petition of the Lord\'s Prayer, '
        "explaining that Scripture distinguishes God's will of decree from His "
        "will of precept, and calling believers to contented submission, "
        "modeled by David and Mary, with an eschatological longing for the "
        'consummation when obedience becomes the heart\'s desire."'
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
        "Sample Speaker examined the third petition of the Lord's Prayer and pressed "
        "believers toward obedient, contented submission to God's will, with an "
        "eschatological hope that obedience becomes delight."
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
        "Sample Speaker opened the third petition of the Lord's Prayer, tracing the "
        "distinction between God's decree and His precepts, and calling for "
        "contented obedience and eschatological hope."
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
