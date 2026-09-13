from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SECONDS = 3600

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


def build_detection_prompt(segments: list[dict[str, Any]], qa_margin_seconds: float = 3.0) -> str:
    transcript_lines = []
    for segment in segments:
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        text = str(segment.get("text", "")).strip()
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
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    text = text.strip()
    first = text.find("{")
    last = text.rfind("}")
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
    auto_edit_config = (config or {}).get("auto_edit", {})
    qa_margin_seconds = float(auto_edit_config.get("qa_margin_seconds", 3.0))
    min_sermon_seconds = float(auto_edit_config.get("min_sermon_seconds", 600))

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
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        response = llm_manager.chat(messages, operation="auto_edit")
        payload = json.loads(_strip_markdown_fences(response))
    except Exception as e:
        logger.warning(f"auto_edit: LLM response unusable, falling back: {e}")
        return _fallback_plan(duration, "Detection fallback: LLM output not usable", "")

    try:
        start = float(payload["start"])
        end = float(payload["end"])
        confidence = float(payload.get("confidence", 0.0))
        evidence = str(payload.get("evidence", ""))
        qa_judgment = str(payload.get("qa_judgment", "cut"))
        reasoning = str(payload.get("reasoning", ""))
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"auto_edit: LLM JSON missing or invalid fields: {e}")
        return _fallback_plan(duration, "Detection fallback: LLM output not usable", "")

    if (
        not (0 <= start < end)
        or not evidence.strip()
        or qa_judgment
        not in (
            "cut",
            "teaching_continues",
        )
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


XFADE_SECONDS = 0.8


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS, check=True
        )
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "")[-400:]
        raise RuntimeError(f"apply_edit ffmpeg failed: {stderr_tail}") from e


def _fmt(seconds: float) -> str:
    return f"{seconds:.3f}"


def apply_edit(
    source: Path,
    plan: EditPlan,
    out: Path,
    logo_path: Path | None = None,
    fade_to_black: bool | None = None,
) -> Path:
    if fade_to_black is None:
        fade_to_black = plan.fade_to_black
    if plan.start < 0 or plan.end <= plan.start:
        raise ValueError(f"invalid edit plan: start={plan.start} end={plan.end}")

    fade_in = max(plan.fade_in, 0.0)
    logo_hold = max(plan.logo_hold, 0.0)
    content_dur = plan.end - plan.start
    fade_out_start = max(content_dur - fade_in, 0.0)

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-ss",
        _fmt(plan.start),
        "-to",
        _fmt(plan.end),
        "-i",
        str(source),
    ]

    filters: list[str] = []
    fade_in_filter = f"fade=t=in:st=0.000:d={_fmt(fade_in)}"

    if logo_path is not None and logo_hold > 0:
        cmd += ["-loop", "1", "-t", _fmt(logo_hold), "-i", str(logo_path)]
        total = content_dur + logo_hold - XFADE_SECONDS
        filters.append(
            f"[0:v]setpts=PTS-STARTPTS,{fade_in_filter},"
            f"fade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},settb=1/25[cv]"
        )
        filters.append("[1:v][cv]scale2ref=w=iw:h=ih[lg0][cvr]")
        filters.append("[lg0]fps=25,settb=1/25[lg]")
        filters.append(
            f"[cvr][lg]xfade=transition=fade:duration={XFADE_SECONDS:.3f}"
            f":offset={_fmt(content_dur - XFADE_SECONDS)}[xv]"
        )
        if fade_to_black:
            end_fade_start = max(total - fade_in, 0.0)
            filters.append(f"[xv]fade=t=out:st={_fmt(end_fade_start)}:d={_fmt(fade_in)}[vout]")
        else:
            filters.append("[xv]null[vout]")
        filters.append(
            f"[0:a]afade=t=in:st=0.000:d={_fmt(fade_in)},"
            f"afade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},apad[aout]"
        )
    else:
        total = content_dur
        video_chain = f"[0:v]setpts=PTS-STARTPTS,{fade_in_filter}"
        if fade_to_black and content_dur > 0:
            audio_chain = (
                f"afade=t=in:st=0.000:d={_fmt(fade_in)},"
                f"afade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},apad"
            )
            video_chain += f",fade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)}"
        else:
            audio_chain = f"afade=t=in:st=0.000:d={_fmt(fade_in)}"
        filters.append(video_chain + "[vout]")
        filters.append(f"[0:a]{audio_chain}[aout]")

    cmd += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-t",
        _fmt(total),
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(out),
    ]

    _run_ffmpeg(cmd)
    return out


def _render_snippet(source: Path, start: float, end: float, out: Path) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        _fmt(start),
        "-to",
        _fmt(end),
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-crf",
        "28",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(out),
    ]
    _run_ffmpeg(cmd)
    return out


def render_review_snippets(
    source: Path,
    plan: EditPlan,
    out_dir: Path,
    logo_path: Path | None = None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    snippets: list[Path] = []

    start_window = (max(plan.start - 10.0, 0.0), plan.start + 10.0)
    end_window = (max(plan.end - 10.0, 0.0), plan.end + 10.0)

    for name, (ws, we) in (("snippet_start.mp4", start_window), ("snippet_end.mp4", end_window)):
        if we - ws >= 0.5:
            try:
                snippets.append(_render_snippet(source, ws, we, out_dir / name))
            except RuntimeError as e:
                logger.warning(f"auto_edit: review snippet {name} failed: {e}")

    span_start = max(plan.start, plan.end - 30.0)
    if plan.end - span_start >= 0.5:
        preview_plan = EditPlan(
            start=span_start,
            end=plan.end,
            fade_in=plan.fade_in,
            logo_hold=plan.logo_hold,
            fade_to_black=True,
        )
        try:
            snippets.append(
                apply_edit(source, preview_plan, out_dir / "snippet_ending.mp4", logo_path)
            )
        except (RuntimeError, ValueError) as e:
            logger.warning(f"auto_edit: ending snippet failed: {e}")

    return snippets
