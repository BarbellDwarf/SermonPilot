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


_REFUSAL_RE = re.compile(
    r"^\s*(?:"
    r"i'?m sorry|i am sorry|"
    r"i can'?t|i cannot|i can not|"
    r"i'?m unable|i am unable|i'?m not able|i am not able|"
    r"i won'?t|i will not|i must decline|i have to decline|"
    r"i don'?t have|i do not have|"
    r"as an ai|as a language model|"
    r"unable to (?:provide|write|generate|produce|summari[sz]e)|"
    r"cannot (?:provide|write|generate|produce|assist|fulfill|summari[sz]e)|"
    r"can'?t (?:provide|write|generate|produce|assist|fulfill|summari[sz]e)|"
    r"no (?:description|summary)(?: (?:was|is) )?(?:available|provided|generated)?"
    r")\b",
    re.IGNORECASE,
)

_PLACEHOLDER_VALUES = {
    "description",
    "summary",
    "sermon description",
    "sermon summary",
    "the description",
    "the summary",
    "n/a",
    "na",
    "none",
    "null",
    "nil",
    "tbd",
    "todo",
    "placeholder",
    "content",
    "text",
    "output",
    "insert description here",
    "description goes here",
    "description here",
    "no description",
    "no description available",
    "no summary",
    "lorem ipsum",
    "example description",
    "sample description",
    "test description",
}

_ELLIPSIS_CHARS = frozenset(".… \t\r\n")


def _looks_like_refusal(text: str) -> bool:
    return bool(_REFUSAL_RE.match(text.strip()))


def _looks_like_placeholder(text: str) -> bool:
    normalized = text.strip().strip(_QUOTE_CHARS).strip("[](){}<>").strip()
    folded = normalized.casefold().rstrip(".!:;,").strip()
    if folded in _PLACEHOLDER_VALUES:
        return True
    if "lorem ipsum" in folded:
        return True
    return bool(normalized) and set(normalized) <= _ELLIPSIS_CHARS


def description_rejection_reason(
    text: str, min_chars: int = MIN_DESCRIPTION_CHARS
) -> str | None:
    """Name why a cleaned description is unusable, or None when it is usable.

    A refusal, a placeholder or stub, model narration, or a reply below
    ``min_chars`` is unusable. The reason is a short phrase safe to put in a
    job log; the raw text is never part of it.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return "empty"
    if len(cleaned) < min_chars:
        return f"too short ({len(cleaned)} chars, minimum {min_chars})"
    if _looks_like_refusal(cleaned):
        return "refusal"
    if _looks_like_placeholder(cleaned):
        return "placeholder"
    if is_meta_commentary(cleaned):
        return "model narration"
    return None


def is_usable_description(text: str, min_chars: int = MIN_DESCRIPTION_CHARS) -> bool:
    return description_rejection_reason(text, min_chars) is None


def validate_description(
    raw: str,
    regenerate: Callable[[], str],
    *,
    min_chars: int = MIN_DESCRIPTION_CHARS,
) -> tuple[str | None, str | None]:
    """Clean and validate a model reply, retrying once when unusable.

    The single validation entry point for every description generator, so the
    pipeline and the console regenerate path cannot drift apart. Returns
    ``(text, reason)``: ``text`` is the cleaned description when it is usable,
    otherwise ``None``; ``reason`` names the rejection and is safe to log.
    Junk (a refusal, stub, placeholder, narration, or a reply below
    ``min_chars``) is never returned as a usable description.
    """
    cleaned = clean_description(raw)
    reason = description_rejection_reason(cleaned, min_chars)
    if reason is None:
        return cleaned, None

    logger.info(
        "description cleanup produced unusable text (%s, %d chars); retrying once",
        reason,
        len(cleaned),
    )
    try:
        retry_cleaned = clean_description(regenerate() or "")
    except Exception as exc:
        logger.warning("description retry failed (%s); rejecting reply", exc)
        return None, reason

    retry_reason = description_rejection_reason(retry_cleaned, min_chars)
    if retry_reason is None:
        return retry_cleaned, None

    logger.warning(
        "description rejected after cleanup and one retry (%s)", retry_reason
    )
    return None, retry_reason


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
