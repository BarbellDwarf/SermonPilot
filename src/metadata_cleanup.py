"""Pure cleanup for model-written free-text metadata.

Some models narrate their own work: they append character counts, "Sentence 1:"
walkthroughs, or "Let me count" notes after the real field value. Those notes
must never be stored, so every model-written free-text field runs through the
functions here before it is persisted. The functions are pure: raw model text
in, cleaned field out.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

logger = logging.getLogger(__name__)

MIN_DESCRIPTION_CHARS = 200

_QUOTE_CHARS = " \t\r\n\"'“”‘’"

_LABEL_RE = re.compile(
    r"^\s*(?:here(?:'s| is| are)\s+(?:the\s+)?|the\s+)?"
    r"(?:final\s+)?(?:sermon\s+)?(?:description|summary|answer|output|text)\s*[:\-]\s*",
    re.IGNORECASE,
)

_INTRO_RE = re.compile(
    r"^\s*(?:sure|okay|alright|of course|certainly)[,!]?\s+", re.IGNORECASE
)

_LABEL_ONLY = {
    "description",
    "summary",
    "answer",
    "output",
    "text",
    "sermon description",
    "sermon summary",
    "final answer",
    "final description",
    "the description",
}

_META_PREFIXES = (
    "let me",
    "i'll",
    "i will",
    "i need to",
    "i should",
    "i must",
    "okay",
    "alright",
    "sure,",
    "here is",
    "here's",
    "here are",
    "the user wants",
    "the task",
    "key points",
    "draft:",
    "final answer",
    "final description",
    "final:",
    "answer:",
    "output:",
    "note:",
    "notes:",
    "analysis:",
    "reasoning:",
)

_META_PATTERNS = (
    re.compile(r"^sentence\s+\d+\s*[:.]", re.IGNORECASE),
    re.compile(r"\blet me count\b", re.IGNORECASE),
    re.compile(r"\b\d[\d,]*\s*(?:chars|characters|words)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:roughly|approximately|about|around|total(?:ing)?|that'?s)\b"
        r"[^.!?]*\b\d[\d,]*\s*(?:chars|characters|words)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:check(?:ing)?|count(?:ing)?|verify(?:ing)?)\b[^.!?]*"
        r"\b(?:chars|characters|words)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:char(?:acter)?|word)\s+count\b", re.IGNORECASE),
)

_HASHTAG_RE = re.compile(r"#\w+")


def _normalize(raw: str) -> str:
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*\n", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _is_label_only(block: str) -> bool:
    return block.strip(" :-#*").casefold() in _LABEL_ONLY


def _strip_label(block: str) -> str:
    block = block.strip()
    block = _LABEL_RE.sub("", block, count=1)
    block = _INTRO_RE.sub("", block, count=1)
    return block.strip(_QUOTE_CHARS).strip()


def is_meta_commentary(segment: str) -> bool:
    """True when a line or sentence talks about the text instead of being it."""
    text = (segment or "").strip().lstrip("-*• \t").strip()
    if not text:
        return False
    lowered = text.casefold()
    if any(lowered.startswith(prefix) for prefix in _META_PREFIXES):
        return True
    return any(pattern.search(text) for pattern in _META_PATTERNS)


def _trim_meta_tail(block: str) -> str:
    kept: list[str] = []
    for sentence in _split_sentences(block):
        if is_meta_commentary(sentence):
            break
        kept.append(sentence)
    return " ".join(kept).strip()


def clean_description(raw: str) -> str:
    """Return only the description paragraph from a raw model reply.

    Leading labels and planning blocks are dropped, a trailing run of
    commentary is cut at the first meta sentence, and whitespace is collapsed.
    """
    text = _normalize(raw)
    if not text:
        return ""
    for block in _split_paragraphs(text):
        block = _strip_label(block)
        if not block or _is_label_only(block):
            continue
        content = _trim_meta_tail(block)
        if content:
            return _collapse(content).strip(_QUOTE_CHARS).strip()
    return ""


def is_usable_description(text: str, min_chars: int = MIN_DESCRIPTION_CHARS) -> bool:
    if not text or len(text) < min_chars:
        return False
    return not is_meta_commentary(text)


def clean_description_with_retry(
    raw: str,
    regenerate: Callable[[], str],
    *,
    min_chars: int = MIN_DESCRIPTION_CHARS,
) -> tuple[str, bool]:
    """Clean a model reply, retrying once when the result is unusable.

    Returns the cleaned description and a ``needs_review`` flag. Raw narration
    is never returned, and a failed retry still returns the best cleaned text
    so the caller can continue.
    """
    cleaned = clean_description(raw)
    if is_usable_description(cleaned, min_chars):
        return cleaned, False

    logger.info(
        "description cleanup produced %d chars from %d; retrying once",
        len(cleaned),
        len(raw or ""),
    )
    try:
        retry_cleaned = clean_description(regenerate() or "")
    except Exception as exc:
        logger.warning("description retry failed (%s); keeping first cleaned text", exc)
        return cleaned, True

    if is_usable_description(retry_cleaned, min_chars):
        return retry_cleaned, False

    best = retry_cleaned if len(retry_cleaned) > len(cleaned) else cleaned
    logger.warning(
        "description marked needs_review: cleanup and retry both unusable (%d chars kept)",
        len(best),
    )
    return best, True


def clean_hashtags(raw: str, max_chars: int = 150) -> str:
    """Return a deduplicated, space-delimited hashtag list with prose removed."""
    tags: list[str] = []
    seen: set[str] = set()
    for tag in _HASHTAG_RE.findall(raw or ""):
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    joined = " ".join(tags)
    if max_chars and len(joined) > max_chars:
        joined = _cut_at_space(joined, max_chars)
    return joined


def clean_title(raw: str) -> str:
    """Return the first content line of a model title reply."""
    text = _normalize(raw)
    if not text:
        return ""
    for line in text.split("\n"):
        line = _strip_label(line.strip())
        if not line or _is_label_only(line) or is_meta_commentary(line):
            continue
        return _collapse(line).strip(_QUOTE_CHARS).strip()
    return ""


def _cut_at_space(text: str, limit: int) -> str:
    truncated = text[:limit]
    space = truncated.rfind(" ")
    if space > 0:
        return truncated[:space].strip()
    return truncated.strip()
