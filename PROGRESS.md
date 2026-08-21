# PROGRESS — fix/pipeline-integrity (TKT-143, TKT-144 sermon_updater portion, TKT-150)

Branch: fix/pipeline-integrity @ origin/master (c684af3)

## Findings log

- [setup] worktree clean, branch created.
- [TKT-143 / AUDIT-009] DONE — library.py `generate_ai_content` now saves the fetched
  transcript via `repo.update_sermon_metadata(sermon_id, {'transcript_text': ...})`.
  The old raw `INSERT OR REPLACE INTO sermon_content` nulled description/hashtags/
  key_topics/summary and hand-built a 6-of-8 FTS row; the repo method upserts only the
  transcript column and calls `_rebuild_fts_row` (all 8 columns). Removed now-unused
  `get_db` import.
- [TKT-143 / AUDIT-011] DONE — `publish_dry_run_sermon` migration rewritten:
  created_at carried over from the draft row (schema-tolerant via PRAGMA), FTS row
  rebuilt across every column present in sermon_search carrying key_topics/summary
  from the draft row, cleanup extended to validation_results/manual_review/
  llm_api_usage (per-table try/except). Kept single-transaction raw SQL because
  repo.save_sermon hardcodes CURRENT_TIMESTAMP on insert (cannot preserve created_at),
  cannot migrate child rows in one transaction, and tests/test_publish_dry_run.py
  exercises this exact path against an in-memory fake schema.
- [TKT-144 / AUDIT-017 partial] DONE — process_new_sermon gained
  `cancel_check: Callable[[], None] | None = None`; checkpoints before the remote
  create (Step 4) and before the local 'processed' save. cancel_check exceptions are
  wrapped in ProcessingCancelledError, handled ahead of the generic except, and
  surfaced as result['cancelled']=True.
- [TKT-144 / AUDIT-018 partial] DONE — `_find_existing_processed_sermon_id()` looks up
  title+speaker+recorded_date with status='processed' and a non-draft ID; found →
  re-upload to that sermon instead of creating a duplicate.
- [TKT-150 / AUDIT-021] DONE — recovery draft persisted locally (files + metadata.json
  + transcript.txt + DB row status='draft') BEFORE create_new_sermon_api; deleted once
  the real record saves; on create failure the result carries draft id/output_dir.
- [TKT-150 / AUDIT-025] DONE — publish_dry_run_sermon checks upload_info.sermonaudio_id
  of the draft; if set, skips creation and uploads to that ID. Newly created IDs are
  recorded immediately after creation so a retried publish cannot duplicate.
- [TKT-150 / AUDIT-026] DONE — _reuse_existing_transcript compares identity of stems
  with the `{epoch_ms}_` UI prefix stripped against metadata.json original_file;
  legacy mtime heuristic kept only for dirs without recorded original_file.
- [TKT-150 / AUDIT-043] DONE — chose transcoding: after enhancement, the enhanced WAV
  is converted back to the input container via ffmpeg (`_transcode_media`, per-container
  codec args with default-encoder fallback); on failure keeps WAV + logs warning
  (pre-existing behavior).
- [TKT-150 / AUDIT-044] DONE — seriesID removed from create_new_sermon_api payload
  (and from its signature); set_sermon_series PATCH is now the single application path
  in both callers.
- [TKT-150 / AUDIT-045] DONE — languageCode resolved from transcription config
  (`_resolve_api_language_code`, whisper_local/faster_whisper_local/openai/openrouter
  sections then top-level), fallback 'eng'.
- [TKT-150 / AUDIT-071] PENDING — job_executors.py cleanup of uploaded copies.

## Decisions

- AUDIT-043 lower-risk option picked: ffmpeg transcode back to input container
  (consistent with existing mux/extract usage) rather than renaming outputs to .wav,
  which would ripple into filenames/metadata/upload types everywhere.
- AUDIT-045 passes the configured value through verbatim ('en' in default config);
  SermonAudio accepts ISO 639 codes here and the previous hardcoded 'eng' remains the
  fallback when unconfigured.

