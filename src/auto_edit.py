from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a precise sermon video editor. You analyse timestamped sermon transcripts and "
    "return strict JSON only. Never wrap the JSON in markdown fences. Never add prose before "
    "or after the JSON."
)


@dataclass
class EditPlan:
    start: float = 0.0
    end: float = 0.0
    fade_in: float = 1.0
    logo_hold: float = 3.0
    fade_to_black: bool = True
    confidence: float = 0.0
    needs_review: bool = True
    evidence: str = "No timestamped transcript available"
    qa_judgment: str = "cut"
    reasoning: str = ""


def _format_timestamp(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def build_detection_prompt(
    segments: list[dict[str, Any]], qa_margin_seconds: float = 3.0
) -> str:
    transcript_lines = []
    for segment in segments:
        start = float(segment.get('start', 0.0) or 0.0)
        end = float(segment.get('end', start) or start)
        text = str(segment.get('text', '')).strip()
        transcript_lines.append(f"[{_format_timestamp(start)}-{_format_timestamp(end)}] {text}")
    transcript = "\n".join(transcript_lines)

    return f"""You are analysing a timestamped transcript of a recorded sermon video.
Identify two cut points so the publisher can trim pre-service content and post-service Q&A
from the uploaded video.

Transcript:
{transcript}

Follow these rules exactly:

1. Identify where the sermon/class TEACHING starts. Ignore pre-service noise, music, prayer,
   announcements, welcome, and Scripture reading unless it is the main body of the teaching.
2. Identify the first transition into OPEN Q&A: the speaker invites questions from the audience
   or the transcript shows an audience question-and-answer cadence (short exchanges, gestures
   like "how do we", audience members speaking).
3. If a question appears but is followed by SUSTAINED FURTHER TEACHING (a multi-minute block of
   exposition), the END point goes AFTER that teaching block closes, and qa_judgment must be
   "teaching_continues".
4. If you cannot tell from the transcript whether teaching continues after a question, set
   needs_review in your reasoning to true and quote the ambiguous lines in evidence.
5. The END point must sit {qa_margin_seconds} seconds BEFORE the first Q&A utterance so no
   question is clipped. Subtract that margin from your natural cut time.
6. Quote the decisive transcript lines in evidence. Evidence is mandatory and must be non-empty.

Respond with STRICT JSON only, in exactly this shape:
{{"start": <seconds>, "end": <seconds>, "confidence": <0-1>, "evidence": "<quoted lines>",
"qa_judgment": "cut"|"teaching_continues", "reasoning": "<short>"}}

Timestamps must be in seconds measured from the start of the recording, matching the transcript
timestamps above."""


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else text
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3]
    text = text.strip()
    first = text.find('{')
    last = text.rfind('}')
    if first != -1 and last > first:
        text = text[first : last + 1]
    return text.strip()


def _fallback_plan(duration: float | None, evidence: str, reasoning: str) -> EditPlan:
    end = duration if duration is not None else 0.0
    return EditPlan(
        start=0.0,
        end=float(end),
        confidence=0.0,
        needs_review=True,
        evidence=evidence,
        qa_judgment="cut",
        reasoning=reasoning,
    )


def detect_cut_points(
    segments: list[dict[str, Any]],
    llm_manager: Any,
    config: dict[str, Any] | None = None,
    duration: float | None = None,
) -> EditPlan:
    auto_edit_config = (config or {}).get('auto_edit', {})
    qa_margin_seconds = float(auto_edit_config.get('qa_margin_seconds', 3.0))
    min_sermon_seconds = float(auto_edit_config.get('min_sermon_seconds', 600))

    if not segments:
        logger.warning("auto_edit: no timestamped segments, returning needs_review plan")
        plan = _fallback_plan(
            duration,
            "No timestamped transcript available",
            "Detection requires timestamped transcript segments",
        )
        plan_needs_review = validate_plan(plan, duration, min_sermon_seconds)
        if plan_needs_review:
            logger.warning(f"auto_edit fallback plan invalid: {plan_needs_review}")
        return plan

    prompt = build_detection_prompt(segments, qa_margin_seconds)
    messages: list[dict[str, str]] = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': prompt},
    ]

    try:
        response = llm_manager.chat(messages, operation='auto_edit')
        payload = json.loads(_strip_markdown_fences(response))
    except Exception as e:
        logger.warning(f"auto_edit: LLM response unusable, falling back: {e}")
        return _fallback_plan(duration, "Detection fallback: LLM output not usable", "")

    try:
        start = float(payload['start'])
        end = float(payload['end'])
        confidence = float(payload.get('confidence', 0.0))
        evidence = str(payload.get('evidence', ''))
        qa_judgment = str(payload.get('qa_judgment', 'cut'))
        reasoning = str(payload.get('reasoning', ''))
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"auto_edit: LLM JSON missing or invalid fields: {e}")
        return _fallback_plan(duration, "Detection fallback: LLM output not usable", "")

    if not (0 <= start < end) or not evidence.strip() or qa_judgment not in (
        'cut',
        'teaching_continues',
    ):
        logger.warning("auto_edit: LLM JSON failed sanity checks, falling back")
        return _fallback_plan(duration, "Detection fallback: LLM output not usable", "")

    if duration is not None:
        end = min(end, float(duration))

    plan = EditPlan(
        start=start,
        end=end,
        confidence=confidence,
        needs_review=False,
        evidence=evidence,
        qa_judgment=qa_judgment,
        reasoning=reasoning,
    )

    problems = validate_plan(plan, duration, min_sermon_seconds)
    if problems:
        logger.warning(f"auto_edit: plan rejected, needs_review: {problems}")
        plan.needs_review = True
        plan.confidence = 0.0

    return plan


def validate_plan(
    plan: EditPlan, duration: float | None = None, min_sermon_seconds: float = 600.0
) -> list[str]:
    problems: list[str] = []

    if plan.start < 0:
        problems.append("start is negative")

    if duration is not None:
        if plan.end > duration + 1.0:
            problems.append("end exceeds video duration")
        if plan.start > duration:
            problems.append("start exceeds video duration")

    if plan.end - plan.start <= 0:
        problems.append("end must be greater than start")
    elif plan.end - plan.start < min_sermon_seconds:
        problems.append(
            f"planned duration {plan.end - plan.start:.1f}s is below minimum "
            f"{min_sermon_seconds:.1f}s"
        )

    return problems
