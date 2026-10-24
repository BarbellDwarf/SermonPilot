# Description Generation Failures

A description that cannot be generated must never become content. Before this
rule, `generate_summary()` returned the literal string `Summary generation
failed` when every provider failed, and callers stored whatever came back, so
the failure text landed in `sermons.description` and read as a success in the
logs.

## The contract

`generate_summary()` either returns usable prose or raises
`DescriptionGenerationError`. It never returns a failure string.

- The provider chain is tried inside `llm_manager.chat()`: primary, then the
  configured fallbacks.
- One retry is added on top for a transient provider failure.
- Typed `LLMTimeoutError`, `LLMModelNotFoundError`, and
  `LLMModelNotConfiguredError` keep their own handling.
- If cleanup and one quality retry still leave nothing usable, the function
  raises instead of returning text.

`DescriptionGenerationError` carries `provider`, `elapsed_seconds`, and
`attempts` so the caller can log the real cause.

## What callers do

- `process_new_sermon()` leaves the description empty, skips the template
  fallback, logs `Description generation failed - retry`, and stores the
  review flag. It never prints a generated-description line for a failure.
- `process_single_sermon()` leaves the stored description unchanged, writes no
  description file, and pushes nothing to SermonAudio.
- `save_sermon()` only writes content columns that are supplied, so a
  metadata-only run cannot blank a stored description or hashtags.

## The review flag

`description_needs_review` is an integer column on `sermons` (added by the
idempotent startup migration). A failed generation sets it to `1`; a
successful generation clears it to `0`. The sermon detail API returns it as
`description_needs_review`, and the console shows
`Description generation failed - retry` next to the description field.

## Retrying by hand

The console retry button calls:

```
POST /api/sermons/{sermon_id}/description/regenerate
```

The route queues a `metadata_update` job through the normal job queue with
`actions: {generate_description: true}`. It never regenerates synchronously,
and it returns `409` when another job for the sermon is already active.

## Per-field generation

Each metadata field the generator produces has its own **Generate** button in
the review details panel:

```
POST /api/sermons/{sermon_id}/metadata/generate
{ "field": "title" | "description" | "hashtags" }
```

The route runs on the request thread with a 300-second wall-clock bound and
returns `{field, value, needs_review}`. It persists the value before returning
so a later Generate & Upload reads it from the row. Generation reads the
transcript cut to the current edit plan's kept ranges, so material the render
drops is never sent to the model; the review panel still shows the full
transcript. A sermon without a
transcript is refused with `detail.code == "no_transcript"`; provider
timeouts, missing models, and unusable output return `504`, `503`, or `502`
with a message the editor shows in place. The console marks a generated value
with a **Generated** chip until the operator types in that field.

## Generate & Upload

The review page's publish action is **Approve · Generate & Upload** (or
**Re-render · Generate & Upload** once published). It sends
`generate_metadata: true` with the apply request. The pipeline fills any empty
title, description, or hashtags before upload and makes no LLM call for fields
that already hold a value. The uploaded transcript is the cut-down transcript
finalized from the applied plan, not the full source transcript.

The new-sermon flow carries the same choice as **Generate metadata on upload**
(`skip_ai_generation` in the payload). It defaults on, matching the previous
default, and the job stores the choice with the submission.

## Budgets and retries

Defaults, read from the resolved config (`llm` block):

| Setting | Default |
| --- | --- |
| `llm.timeout_seconds` (per provider call) | 120s |
| `llm.connect_timeout_seconds` | 10s |
| `llm.total_budget_seconds` (primary + fallbacks) | 300s |
| `llm.metadata_stage_budget_seconds` | 900s |
| Description provider attempts | 2 |

Long inputs use map-reduce: transcripts over 24,000 characters are summarized
in ~12,000-character chunks first, then the final prompt is built from the
chunk summaries.
