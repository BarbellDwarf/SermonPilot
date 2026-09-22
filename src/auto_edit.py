from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SECONDS = 3600

DETECTION_OK = "ok"
DETECTION_UNAVAILABLE = "unavailable"

_DEFAULT_MAX_TRANSCRIPT_CHARS = 24000
_CHARS_PER_TOKEN = 3.5
_OUTPUT_TOKEN_RESERVE = 2048
_ELISION_MARKER = "[... middle of the transcript elided to fit the model context ...]"

DEFAULT_DETECTION_SYSTEM_PROMPT = (
    "You are a precise sermon video editor. You analyse timestamped sermon transcripts and "
    "return strict JSON only. Never wrap the JSON in markdown fences. Never add prose before "
    "or after the JSON."
)

SYSTEM_PROMPT = DEFAULT_DETECTION_SYSTEM_PROMPT

DETECTION_TEMPLATE_NAME = "cut_detection"

# Built-in detection prompt. Placeholders ({transcript}, {elision_note},
# {refinement}, {qa_margin_seconds}) are substituted by _render_template, which
# only touches ``{word}`` tokens, so the literal JSON braces below survive.
DEFAULT_DETECTION_USER_PROMPT = """\
You are analysing a timestamped transcript of a recorded sermon video.
Identify two cut points so the publisher can trim pre-service content and post-service Q&A
from the uploaded video.

Transcript:
{transcript}
{elision_note}
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
{refinement}
Respond with the JSON object FIRST, before any explanation. Do not write analysis,
commentary, or working notes. Respond with STRICT JSON only, in exactly this shape:
{"start": <seconds>, "end": <seconds>, "confidence": <0-1>, "evidence": "<quoted lines>",
"qa_judgment": "cut"|"teaching_continues", "reasoning": "<short>"}

Timestamps must be in seconds measured from the start of the recording, matching the transcript
timestamps above."""


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
    audio_offset: float = 0.0
    detection_status: str = DETECTION_OK


def _format_timestamp(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _bound_transcript(lines: list[str], max_chars: int | None) -> tuple[str, bool]:
    """Join transcript lines, eliding the middle when the character budget is exceeded.

    Cut detection needs the opening (where teaching starts) and the closing
    (where Q&A starts), so the whole-transcript shape is preserved by keeping
    a head and a tail and replacing the middle with a marker. Returns the
    joined text and whether anything was elided.
    """
    transcript = "\n".join(lines)
    if not max_chars or max_chars <= 0 or len(transcript) <= max_chars:
        return transcript, False

    budget = max_chars - len(_ELISION_MARKER) - 2
    if budget <= 0:
        return transcript[:max_chars], True

    head_budget = budget // 2
    tail_budget = budget - head_budget

    head: list[str] = []
    used = 0
    for line in lines:
        if used + len(line) + 1 > head_budget:
            break
        head.append(line)
        used += len(line) + 1

    tail: list[str] = []
    used = 0
    for line in reversed(lines):
        if used + len(line) + 1 > tail_budget:
            break
        tail.append(line)
        used += len(line) + 1
    tail.reverse()

    if len(head) + len(tail) >= len(lines):
        return transcript, False

    return "\n".join(head + [_ELISION_MARKER] + tail), True


_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _render_template(template: str, values: dict[str, Any]) -> str:
    """Substitute ``{word}`` placeholders, leaving unknown tokens untouched.

    Regex substitution (not ``str.format``) keeps literal JSON braces in the
    detection prompt intact and never raises on an unknown placeholder.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return _TEMPLATE_PLACEHOLDER_RE.sub(_replace, template)


def resolve_detection_template(config: dict[str, Any] | None) -> dict[str, str] | None:
    """Return the configured cut-detection prompt template, or None to use defaults.

    A missing, disabled, or blank template falls back to the built-in prompt.
    """
    templates = (config or {}).get("prompt_templates") or {}
    tmpl = templates.get(DETECTION_TEMPLATE_NAME) if isinstance(templates, dict) else None
    if not isinstance(tmpl, dict) or not tmpl.get("enabled", True):
        return None
    user_text = str(tmpl.get("user") or "")
    if not user_text.strip():
        return None
    return {
        "system": str(tmpl.get("system") or "") or DEFAULT_DETECTION_SYSTEM_PROMPT,
        "user": user_text,
    }


def build_detection_prompt(
    segments: list[dict[str, Any]],
    qa_margin_seconds: float = 3.0,
    previous_plan: dict[str, Any] | None = None,
    rejection_notes: str | None = None,
    max_transcript_chars: int | None = None,
    template: dict[str, str] | None = None,
) -> str:
    transcript_lines = []
    for segment in segments:
        start = float(segment.get("start", 0.0) or 0.0)
        end = float(segment.get("end", start) or start)
        text = str(segment.get("text", "")).strip()
        transcript_lines.append(f"[{_format_timestamp(start)}-{_format_timestamp(end)}] {text}")
    transcript, elided = _bound_transcript(transcript_lines, max_transcript_chars)
    if elided:
        logger.info(
            "auto_edit: transcript bounded to %d chars (middle elided) to fit the model context",
            max_transcript_chars,
        )
    elision_note = (
        "\nNote: the transcript was shortened to fit the model context and the middle "
        "was elided. Derive the cut points from the excerpts shown.\n"
        if elided
        else ""
    )

    refinement = ""
    if previous_plan is not None or rejection_notes:
        prev_start = previous_plan.get("start") if previous_plan else None
        prev_end = previous_plan.get("end") if previous_plan else None
        prev_evidence = (previous_plan.get("evidence") if previous_plan else "") or ""
        notes = (rejection_notes or "").strip()
        refinement = f"""

This is a RE-DETECTION. The publisher rejected the previous proposal and gave notes.
Treat the notes as the user's editing instructions, not just a timestamp tweak: they may
redefine WHICH content to include or exclude entirely (for example, skip an earlier
class when two are recorded back to back, or keep only a later session). Honour the
notes first, then re-derive start and end from the transcript.

Previous proposal:
- start: {prev_start}
- end: {prev_end}
- evidence: {prev_evidence[:400]}

Publisher notes (authoritative):
"{notes}"

Re-propose start and end so they satisfy the notes, and quote FRESH transcript lines
as evidence for the new proposal. Do not reuse the previous evidence."""

    user_template = (template or {}).get("user") or DEFAULT_DETECTION_USER_PROMPT
    return _render_template(
        user_template,
        {
            "transcript": transcript,
            "elision_note": elision_note,
            "refinement": refinement,
            "qa_margin_seconds": qa_margin_seconds,
        },
    )


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    """Return the first JSON object that carries ``start`` and ``end``.

    Models commonly wrap the payload in reasoning prose or markdown fences,
    and may emit a stray ``{`` before the real object. Scan each brace
    position with a real decoder and keep the first object whose shape matches
    an edit plan, so a verbose model still parses.
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        brace = text.find("{", index)
        if brace == -1:
            return None
        try:
            payload, end = decoder.raw_decode(text, brace)
        except json.JSONDecodeError:
            index = brace + 1
            continue
        if isinstance(payload, dict) and "start" in payload and "end" in payload:
            return payload
        index = max(end, brace + 1)
    return None


def _preview(text: str, limit: int = 300) -> str:
    return (text or "").strip().replace("\n", " ")[:limit]


def _iter_providers(llm_manager: Any) -> list[Any]:
    providers: list[Any] = []
    primary = getattr(llm_manager, "primary_provider", None)
    if primary is not None:
        providers.append(primary)
    providers.extend(getattr(llm_manager, "fallback_providers", None) or [])
    validator = getattr(llm_manager, "validator_provider", None)
    if validator is not None:
        providers.append(validator)
    providers.extend((getattr(llm_manager, "operation_providers", None) or {}).values())
    return providers


def _resolve_transcript_char_budget(
    config: dict[str, Any] | None, llm_manager: Any
) -> int:
    """Bound the transcript to the smallest model context actually configured.

    ``num_ctx`` counts prompt plus generated tokens, so reserve room for the
    reply and convert the remainder to characters with a conservative ratio.
    An explicit ``auto_edit.max_transcript_chars`` always wins.
    """
    auto_edit_config = (config or {}).get("auto_edit", {}) or {}
    explicit = auto_edit_config.get("max_transcript_chars")
    try:
        if explicit is not None and int(explicit) > 0:
            return int(explicit)
    except (TypeError, ValueError):
        pass

    contexts = [
        int(provider.num_ctx)
        for provider in _iter_providers(llm_manager)
        if isinstance(getattr(provider, "num_ctx", None), int)
        and int(provider.num_ctx) > 0
    ]
    if not contexts:
        return _DEFAULT_MAX_TRANSCRIPT_CHARS
    usable_tokens = max(min(contexts) - _OUTPUT_TOKEN_RESERVE, 1024)
    return max(4000, int(usable_tokens * _CHARS_PER_TOKEN))


def _provider_summary(llm_manager: Any) -> str:
    try:
        info = llm_manager.get_provider_info()
    except Exception:
        info = {}
    parts: list[str] = []
    primary = info.get("primary") or {}
    if primary:
        parts.append(f"primary={primary.get('type')}/{primary.get('model')}")
    for fallback in info.get("fallback") or []:
        parts.append(f"fallback={fallback.get('type')}/{fallback.get('model')}")
    return ", ".join(parts) or "unknown"


def _unavailable_plan(evidence: str, reasoning: str) -> EditPlan:
    return EditPlan(
        start=0.0,
        end=0.0,
        confidence=0.0,
        needs_review=True,
        evidence=evidence,
        qa_judgment="cut",
        reasoning=reasoning,
        detection_status=DETECTION_UNAVAILABLE,
    )


def detect_cut_points(
    segments: list[dict[str, Any]],
    llm_manager: Any,
    config: dict[str, Any] | None = None,
    duration: float | None = None,
    previous_plan: dict[str, Any] | None = None,
    rejection_notes: str | None = None,
) -> EditPlan:
    auto_edit_config = (config or {}).get("auto_edit", {})
    qa_margin_seconds = float(auto_edit_config.get("qa_margin_seconds", 3.0))
    min_sermon_seconds = float(auto_edit_config.get("min_sermon_seconds", 600))
    max_transcript_chars = _resolve_transcript_char_budget(config, llm_manager)

    if not segments:
        logger.error("auto_edit: cut detection unavailable: no timestamped transcript segments")
        return _unavailable_plan(
            "Cut detection failed: no timestamped transcript was available.",
            "Detection requires timestamped transcript segments",
        )

    template = resolve_detection_template(config)
    prompt = build_detection_prompt(
        segments,
        qa_margin_seconds,
        previous_plan=previous_plan,
        rejection_notes=rejection_notes,
        max_transcript_chars=max_transcript_chars,
        template=template,
    )
    prompt_chars = len(prompt)
    system_prompt = (template or {}).get("system") or DEFAULT_DETECTION_SYSTEM_PROMPT
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    provider_summary = _provider_summary(llm_manager)

    plan: EditPlan | None = None
    last_response = ""
    last_error = ""
    for attempt in range(1, 4):
        started = time.monotonic()
        try:
            response = llm_manager.chat(messages, operation="auto_edit")
        except Exception as e:
            last_error = f"{type(e).__name__}: {_preview(str(e))}"
            logger.warning(
                "auto_edit: attempt %d/3 call failed (provider=%s prompt_chars=%d "
                "elapsed=%.1fs): %s",
                attempt,
                provider_summary,
                prompt_chars,
                time.monotonic() - started,
                last_error,
            )
            continue

        last_response = response or ""
        logger.info(
            "auto_edit: attempt %d/3 returned (provider=%s prompt_chars=%d "
            "response_chars=%d elapsed=%.1fs)",
            attempt,
            provider_summary,
            prompt_chars,
            len(last_response),
            time.monotonic() - started,
        )

        payload = _extract_json_payload(last_response)
        if payload is None:
            last_error = "no parsable JSON payload"
            logger.warning(
                "auto_edit: attempt %d/3 returned no parsable JSON (preview=%r)",
                attempt,
                _preview(last_response),
            )
            continue

        try:
            start = float(payload["start"])
            end = float(payload["end"])
            confidence = float(payload.get("confidence", 0.0))
            evidence = str(payload.get("evidence", ""))
            qa_judgment = str(payload.get("qa_judgment", "cut"))
            reasoning = str(payload.get("reasoning", ""))
        except (KeyError, TypeError, ValueError) as e:
            last_error = f"invalid JSON fields: {e}"
            logger.warning(
                "auto_edit: attempt %d/3 JSON fields invalid: %s", attempt, last_error
            )
            continue

        if (
            not (0 <= start < end)
            or not evidence.strip()
            or qa_judgment
            not in (
                "cut",
                "teaching_continues",
            )
        ):
            last_error = "JSON failed sanity checks"
            logger.warning("auto_edit: attempt %d/3 JSON failed sanity checks", attempt)
            continue

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
        break

    if plan is None:
        detail = last_error or "no usable JSON payload"
        logger.error(
            "auto_edit: cut detection UNAVAILABLE after 3 attempts (provider=%s "
            "prompt_chars=%d last_error=%s). Last raw response preview "
            "(scrubbed, truncated): %r",
            provider_summary,
            prompt_chars,
            detail,
            _preview(last_response),
        )
        return _unavailable_plan(
            "Cut detection failed; no usable cut points were returned. "
            "Set the cuts manually or re-run detection.",
            detail,
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

    if abs(float(plan.audio_offset or 0.0)) > MAX_AUDIO_OFFSET:
        problems.append(
            f"audio offset {plan.audio_offset:+.1f}s exceeds limit "
            f"±{MAX_AUDIO_OFFSET:.1f}s"
        )

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
MAX_AUDIO_OFFSET = 5.0
DEFAULT_FADE_OUT_TAIL_SECONDS = 2.0


def _run_ffmpeg(cmd: list[str]) -> None:
    import time as _time

    start = _time.time()
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS, check=True
        )
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or "")[-400:]
        raise RuntimeError(f"apply_edit ffmpeg failed: {stderr_tail}") from e
    finally:
        logger.info(
            "ffmpeg stage %.1fs: %s -> %s",
            _time.time() - start,
            " ".join(cmd[:2]),
            cmd[-1],
        )


def _fmt(seconds: float) -> str:
    return f"{seconds:.3f}"


def _resolve_tail(source: Path, end: float, d_pos: float, fade_out_tail_seconds: float) -> float:
    wanted = max(float(fade_out_tail_seconds), 0.0)
    if wanted <= 0:
        return 0.0
    ffprobe = shutil.which("ffprobe")
    src_dur: float | None = None
    if ffprobe:
        try:
            src_dur = _ffprobe_duration(ffprobe, source)
        except Exception:
            src_dur = None
    if src_dur is None:
        return 0.0
    return min(wanted, max(0.0, src_dur - end - d_pos))


def apply_edit(
    source: Path,
    plan: EditPlan,
    out: Path,
    logo_path: Path | None = None,
    fade_to_black: bool | None = None,
    fade_out_tail_seconds: float = DEFAULT_FADE_OUT_TAIL_SECONDS,
) -> Path:
    if fade_to_black is None:
        fade_to_black = plan.fade_to_black
    if plan.start < 0 or plan.end <= plan.start:
        raise ValueError(f"invalid edit plan: start={plan.start} end={plan.end}")

    fade_in = max(plan.fade_in, 0.0)
    logo_hold = max(plan.logo_hold, 0.0)
    content_dur = plan.end - plan.start

    audio_offset = float(plan.audio_offset or 0.0)
    d_pos = max(audio_offset, 0.0)
    tail = _resolve_tail(source, plan.end, d_pos, fade_out_tail_seconds)
    window_end = plan.end + tail + d_pos
    out_len = window_end - plan.start
    fade_out_start = max(out_len - fade_in, 0.0)

    out.parent.mkdir(parents=True, exist_ok=True)

    pts_shift = ""
    if abs(audio_offset) > 1e-6:
        sign = "+" if audio_offset > 0 else "-"
        pts_shift = f",asetpts=PTS{sign}{abs(audio_offset):.3f}/TB"

    cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-ss",
        _fmt(plan.start),
        "-to",
        _fmt(window_end),
        "-i",
        str(source),
    ]

    filters: list[str] = []
    fade_in_filter = f"fade=t=in:st=0.000:d={_fmt(fade_in)}"

    if logo_path is not None and logo_hold > 0:
        cmd += ["-loop", "1", "-t", _fmt(logo_hold), "-i", str(logo_path)]
        ffprobe = shutil.which("ffprobe")
        src_fps = _ffprobe_frame_rate(ffprobe, source) if ffprobe else None
        fps_expr = src_fps or "30"
        tb_expr = f"1/{fps_expr.split('/')[0]}"
        total = out_len + logo_hold - XFADE_SECONDS
        filters.append(
            f"[0:v]setpts=PTS-STARTPTS,{fade_in_filter},"
            f"fade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},"
            f"fps={fps_expr},settb={tb_expr}[cv]"
        )
        filters.append("[1:v][cv]scale2ref=w=iw:h=ih[lg0][cvr]")
        filters.append(f"[lg0]fps={fps_expr},settb={tb_expr}[lg]")
        filters.append(
            f"[cvr][lg]xfade=transition=fade:duration={XFADE_SECONDS:.3f}"
            f":offset={_fmt(out_len - XFADE_SECONDS)}[xv]"
        )
        if fade_to_black:
            end_fade_start = max(total - fade_in, 0.0)
            filters.append(f"[xv]fade=t=out:st={_fmt(end_fade_start)}:d={_fmt(fade_in)}[vout]")
        else:
            filters.append("[xv]null[vout]")
        filters.append(
            f"[0:a]afade=t=in:st=0.000:d={_fmt(fade_in)}{pts_shift},"
            f"afade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},apad[aout]"
        )
    else:
        total = out_len
        video_chain = f"[0:v]setpts=PTS-STARTPTS,{fade_in_filter}"
        if fade_to_black and content_dur > 0:
            audio_chain = (
                f"afade=t=in:st=0.000:d={_fmt(fade_in)}{pts_shift},"
                f"afade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)},apad"
            )
            video_chain += f",fade=t=out:st={_fmt(fade_out_start)}:d={_fmt(fade_in)}"
        else:
            audio_chain = f"afade=t=in:st=0.000:d={_fmt(fade_in)}{pts_shift}"
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


def shift_snippet_audio(base: Path, offset: float, out: Path) -> Path:
    """Remux a snippet with the audio track shifted by offset seconds.

    No re-encode: both streams are copied, so repeated nudges are near-instant.
    Positive offset delays the audio later; negative advances it.
    """
    if abs(offset) < 1e-6:
        return base
    cmd = [
        "ffmpeg", "-y",
        "-i", str(base),
        "-itsoffset", _fmt(offset), "-i", str(base),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c", "copy",
    ]
    ffprobe = shutil.which("ffprobe")
    base_dur: float | None = None
    if ffprobe:
        try:
            base_dur = _ffprobe_duration(ffprobe, base)
        except Exception:
            base_dur = None
    if base_dur is not None:
        cmd += ["-t", _fmt(base_dur + max(offset, 0.0))]
    else:
        cmd += ["-shortest"]
    cmd += [str(out)]
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
    fade_out_tail_seconds: float = DEFAULT_FADE_OUT_TAIL_SECONDS,
) -> list[Path]:
    if getattr(plan, "detection_status", DETECTION_OK) == DETECTION_UNAVAILABLE:
        logger.info("auto_edit: no review snippets for unavailable cut detection")
        return []
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
            fade_to_black=plan.fade_to_black,
        )
        try:
            snippets.append(
                apply_edit(
                    source,
                    preview_plan,
                    out_dir / "snippet_ending.mp4",
                    logo_path,
                    fade_out_tail_seconds=fade_out_tail_seconds,
                )
            )
        except (RuntimeError, ValueError) as e:
            logger.warning(f"auto_edit: ending snippet failed: {e}")

    return snippets


_KG = 1024**3
_keeper_encoder_cache: tuple[str, list[str]] | None = None


def _probe_nvenc() -> bool:
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-t",
        "0.3",
        "-i",
        "color=c=black:s=256x256:r=25",
        "-c:v",
        "h264_nvenc",
        "-f",
        "null",
        "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).returncode == 0
    except Exception:
        return False


def _probe_vaapi() -> str | None:
    if not Path("/dev/dri").exists():
        return None
    for node in sorted(Path("/dev/dri").glob("renderD*")):
        cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-vaapi_device",
            str(node),
            "-f",
            "lavfi",
            "-t",
            "0.3",
            "-i",
            "color=c=black:s=256x256:r=25",
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            "h264_vaapi",
            "-qp",
            "26",
            "-f",
            "null",
            "-",
        ]
        try:
            if subprocess.run(cmd, capture_output=True, text=True, timeout=20).returncode == 0:
                return str(node)
        except Exception:
            continue
    return None


def detect_hardware_encoder() -> tuple[str, list[str]]:
    global _keeper_encoder_cache
    if _keeper_encoder_cache is not None:
        return _keeper_encoder_cache

    if not shutil.which("ffmpeg"):
        result: tuple[str, list[str]] = ("libx264", [])
    elif shutil.which("nvidia-smi") and _probe_nvenc():
        result = ("h264_nvenc", [])
    else:
        node = _probe_vaapi()
        if node:
            result = ("h264_vaapi", ["-vaapi_device", node])
        else:
            result = ("libx264", [])

    _keeper_encoder_cache = result
    return result


def _ffprobe_duration(ffprobe: str, path: Path) -> float | None:
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def _ffprobe_frame_rate(ffprobe: str, path: Path) -> str | None:
    """Return the video stream frame rate as 'num' or 'num/den', or None on failure."""
    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,avg_frame_rate",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        streams = (json.loads(proc.stdout) or {}).get("streams") or []
        if not streams:
            return None
        raw = streams[0].get("r_frame_rate") or streams[0].get("avg_frame_rate") or ""
        if not raw or raw in ("0/0", "N/A"):
            return None
        num, _, den = str(raw).partition("/")
        if not num.isdigit() or not int(num):
            return None
        den = den.strip()
        if den in ("", "1"):
            return num
        if not den.isdigit() or not int(den):
            return None
        return f"{num}/{den}"
    except Exception:
        return None


def verify_keeper(source: Path, keeper: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not keeper.exists() or not keeper.is_file():
        return False
    try:
        src_dur = _ffprobe_duration(ffprobe, source)
        keep_dur = _ffprobe_duration(ffprobe, keeper)
        if src_dur is None or keep_dur is None:
            return False
        if abs(src_dur - keep_dur) > 2.0:
            return False
        streams = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(keeper),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if streams.returncode != 0:
            return False
        types = set(streams.stdout.split())
        if not {"video", "audio"} <= types:
            return False
        return keeper.stat().st_size > 1_000_000
    except Exception:
        return False


def _keeper_quality_args(encoder: str, crf: int) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-cq", str(crf)]
    if encoder == "h264_vaapi":
        return ["-qp", str(crf + 2)]
    return ["-crf", str(crf)]


def _keeper_preset_args(encoder: str) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-preset", "p1"]
    if encoder == "h264_vaapi":
        return []
    return ["-preset", "veryfast"]


def transcode_to_keeper(source: Path, out: Path, config: dict[str, Any]) -> Path | None:
    keeper_cfg = config.get("auto_edit", {}).get("keeper", {})
    if not keeper_cfg.get("enabled", True):
        return source
    min_gb = float(keeper_cfg.get("min_source_gb", 2.0))
    try:
        source_size = source.stat().st_size
    except OSError as e:
        logger.warning(f"auto_edit keeper: source inaccessible, skipping: {e}")
        return source
    if source_size < min_gb * _KG:
        return source

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("auto_edit keeper: ffmpeg not found, skipping keeper transcode")
        return source

    encoder, extra_args = detect_hardware_encoder()
    crf = int(keeper_cfg.get("crf", 20))
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg, "-y", *extra_args, "-i", str(source)]
    if encoder == "h264_vaapi":
        cmd += ["-vf", "format=nv12,hwupload"]
    else:
        cmd += ["-pix_fmt", "yuv420p"]
    cmd += [
        "-c:v",
        encoder,
        *_keeper_quality_args(encoder, crf),
        *_keeper_preset_args(encoder),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        str(out),
    ]
    logger.info(f"auto_edit keeper: transcoding {source.name} with {encoder}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if proc.returncode != 0:
            logger.warning(f"auto_edit keeper: ffmpeg failed: {(proc.stderr or '')[-400:]}")
            return source
    except Exception as e:
        logger.warning(f"auto_edit keeper: transcode failed, keeping original: {e}")
        return source

    if not verify_keeper(source, out):
        logger.warning("auto_edit keeper: output failed integrity check, keeping original")
        return source
    return out


def should_delete_original(
    source: Path, keeper: Path, config: dict[str, Any], has_applied_plan: bool
) -> bool:
    keeper_cfg = config.get("auto_edit", {}).get("keeper", {})
    if not keeper_cfg.get("delete_original", False):
        return False
    min_gb = float(keeper_cfg.get("min_source_gb", 2.0))
    try:
        if source.stat().st_size < min_gb * _KG:
            return False
    except OSError:
        return False
    if not verify_keeper(source, keeper):
        return False
    return has_applied_plan


def trash_original_after_edit(
    source: Path,
    keeper: Path,
    config: dict[str, Any],
    has_applied_plan: bool,
    **trash_kwargs: Any,
) -> Any:
    """Move the original into trash when every delete-original gate passes.

    ``should_delete_original`` stays the pure predicate; this is the only
    supported way to act on it, so replacing the original is always a
    recoverable move rather than an unlink. Returns the trash record, or
    ``None`` when the gates say to keep the original.
    """
    if not should_delete_original(source, keeper, config, has_applied_plan):
        return None
    try:
        from src.safe_delete import trash_local
    except ImportError:  # src dir placed directly on sys.path
        from safe_delete import trash_local  # type: ignore[no-redef]

    return trash_local(
        source,
        reason="auto_edit_keeper_replaced_original",
        **trash_kwargs,
    )
