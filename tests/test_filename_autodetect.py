"""Tests for filename metadata auto-detection parsing."""

from datetime import date

from ui.sermon_metadata import parse_sermon_filename


def test_full_format():
    parsed = parse_sermon_filename("My Sermon - Romans - Paul - 2026-08-20.mp4")
    assert parsed == {
        "title": "My Sermon",
        "series": "Romans",
        "speaker": "Paul",
        "date": date(2026, 8, 20),
    }


def test_title_only():
    parsed = parse_sermon_filename("Evening Prayer.mp4")
    assert parsed["title"] == "Evening Prayer"
    assert parsed["series"] is None
    assert parsed["speaker"] is None
    assert parsed["date"] is None


def test_title_and_series():
    parsed = parse_sermon_filename("Sermon - Galatians.mp3")
    assert parsed["title"] == "Sermon"
    assert parsed["series"] == "Galatians"
    assert parsed["speaker"] is None
    assert parsed["date"] is None


def test_missing_date_keeps_positions():
    parsed = parse_sermon_filename("T -  - Paul - .mp4")
    assert parsed["title"] == "T"
    assert parsed["series"] is None
    assert parsed["speaker"] == "Paul"
    assert parsed["date"] is None


def test_more_than_four_segments_ignores_extras():
    parsed = parse_sermon_filename("A - B - C - 2026-01-02 - extra.mp4")
    assert parsed["title"] == "A"
    assert parsed["series"] == "B"
    assert parsed["speaker"] == "C"
    assert parsed["date"] == date(2026, 1, 2)


def test_date_formats():
    assert parse_sermon_filename("A - B - C - 2026_08_20.mp3")["date"] == date(2026, 8, 20)
    assert parse_sermon_filename("A - B - C - 08-20-2026.mp3")["date"] == date(2026, 8, 20)
    assert parse_sermon_filename("A - B - C - 8_20_2026.mp3")["date"] == date(2026, 8, 20)


def test_invalid_dates_left_alone():
    for name in (
        "A - B - C - 2026-02-30.mp3",
        "A - B - C - 13-13-2026.mp3",
        "A - B - C - not-a-date.mp3",
    ):
        assert parse_sermon_filename(name)["date"] is None


def test_segments_are_stripped():
    parsed = parse_sermon_filename("  Spaced Title  -  Series X  -  Speaker  - 2026-08-20.mp3")
    assert parsed["title"] == "Spaced Title"
    assert parsed["series"] == "Series X"
    assert parsed["speaker"] == "Speaker"


def test_no_separator_title_only():
    parsed = parse_sermon_filename("My Sermon.mp3")
    assert parsed["title"] == "My Sermon"
    assert parsed["series"] is None
