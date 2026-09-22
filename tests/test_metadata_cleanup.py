"""Tests for cleaning model-written free-text metadata fields."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _path in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from src.metadata_cleanup import (  # noqa: E402
    clean_description,
    clean_description_with_retry,
    clean_hashtags,
    clean_title,
)

GOOD = (
    "Pastor Example Speaker teaches on the biblical doctrine of work, concluding "
    "with Matthew 5:16 and Colossians 3:23-24, where believers are called to "
    "labor 'as unto the Lord' and not merely for men, so their diligent work "
    "shines before others. A discussion followed on vocation versus career and "
    "the temptation to chase status, closing with a call to work faithfully, "
    "rest rightly, and prepare for worship."
)

NARRATION = (
    "Let me count characters roughly. That's about 1,180 characters. Let me count "
    "more carefully. Sentence 1: \"Pastor Example Speaker teaches on the biblical "
    "doctrine of work, concluding with Matthew 5:16 and Colossians 3:23-24, where "
    "believers are called to labor 'as unto the Lord' and not merely for men, so "
    "their diligent work shines before others.\" - roughly 270 chars."
)

LEAKED = GOOD + "\n\n" + NARRATION


def test_leaked_text_cleans_to_first_paragraph():
    result = clean_description(LEAKED)

    assert result == GOOD
    assert "Let me count" not in result
    assert "roughly" not in result
    assert "chars" not in result
    assert "Sentence 1:" not in result


def test_trailing_narration_in_same_block_is_cut():
    inline = GOOD + " Let me count characters roughly. That's about 1,180 characters."

    assert clean_description(inline) == GOOD


def test_clean_description_passes_through_unchanged():
    assert clean_description(GOOD) == GOOD


def test_leading_label_and_quotes_are_stripped():
    raw = 'Here is the description: "' + GOOD + '"'

    assert clean_description(raw) == GOOD


def test_commentary_only_cleans_to_empty():
    assert clean_description(NARRATION) == ""


def test_only_commentary_triggers_exactly_one_retry():
    calls: list[str] = []

    def regenerate() -> str:
        calls.append("retry")
        return GOOD

    result, needs_review = clean_description_with_retry(NARRATION, regenerate)

    assert result == GOOD
    assert calls == ["retry"]
    assert needs_review is False


def test_clean_input_does_not_trigger_retry():
    def regenerate() -> str:  # pragma: no cover - must not run
        raise AssertionError("regenerate should not be called")

    result, needs_review = clean_description_with_retry(GOOD, regenerate)

    assert result == GOOD
    assert needs_review is False


def test_failed_retry_keeps_best_cleaned_text_and_flags_review():
    result, needs_review = clean_description_with_retry(
        NARRATION, lambda: "A short but real description."
    )

    assert result == "A short but real description."
    assert needs_review is True


def test_retry_exception_never_escapes():
    def regenerate() -> str:
        raise RuntimeError("model unavailable")

    result, needs_review = clean_description_with_retry(NARRATION, regenerate)

    assert result == ""
    assert needs_review is True


def test_hashtags_stay_a_clean_list():
    raw = (
        "#Faith #Work Here are the hashtags: #Work #ChristianLiving. "
        "Let me count: 4 tags, roughly 40 characters."
    )

    assert clean_hashtags(raw) == "#Faith #Work #ChristianLiving"


def test_hashtags_dedupe_case_insensitively():
    assert clean_hashtags("#Faith #faith #FAITH") == "#Faith"


def test_hashtags_drop_commentary_without_hashes():
    assert clean_hashtags("Let me count the characters. I'll produce some tags.") == ""


def test_title_drops_label_quotes_and_narration_line():
    assert clean_title('Description: "Work for God, Not Man"') == "Work for God, Not Man"
    assert (
        clean_title("Work for God, Not Man\nLet me count the characters: 25.")
        == "Work for God, Not Man"
    )


def test_title_commentary_only_is_empty():
    assert clean_title("Let me think about a title. I'll count characters.") == ""
