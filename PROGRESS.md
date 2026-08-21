# TKT-145/146/159 Progress — db/jobs integrity

Branch: fix/db-jobs-integrity (base origin/master 393463a)
Worktree: /tmp/opencode/wt-cfg

- [x] TKT-145: transcript stripped at persistence (`_result_for_persistence`) and at source (executor trims key)
- [x] TKT-145: llm_api_usage pruned by cleanup_old_records (days param)
- [x] TKT-145: Clear Completed also removes FAILED; prune_old_jobs(30d) runs at queue start
- [x] TKT-146: WAL pragma at database init
- [x] TKT-146: SQLite writes moved out of queue lock (add_job, _get_next_job, cancel_job, retry_job, _recover_orphaned_jobs, clear_completed_jobs)
- [x] TKT-159: UTC timestamps: `utcnow()` helper; all 21 local now() DB writes/comparisons in database.py are UTC (naive format keeps parity with legacy rows)
- [x] TKT-159: FTS5 MATCH input sanitization (`sanitize_fts_query`, quoted tokens, empty input returns [])
- [x] TKT-159: 6 indexes added in init_database
- [x] TKT-159: favorite/notes updates skip FTS rebuild (update_sermon_metadata rebuilds only when title/speaker/content changed)
- [x] Run test suite + ruff, verify WAL takes effect

## TKT-159 UTC decision

All new explicit writes use naive UTC (`utcnow()`), matching the
`CURRENT_TIMESTAMP` (UTC) defaults that already populate created_at columns
and llm_api_usage.timestamp. This fixes the clearly-wrong comparisons:
get_llm_usage_summary/get_llm_usage_by_operation compared a local-time
cutoff against UTC-stored rows, excluding recent rows by the UTC offset.
Legacy rows written with local time keep their stored values; for cache
expiry and pruning they are now off by the timezone offset at worst, which
is safer than the previous mixed comparison. No data migration performed.

## Verification (32/32 ad-hoc checks, /tmp/opencode/verify_dbjobs.py)

- WAL: fresh sqlite3 connection reports journal_mode=wal; migrate_db copy too
- Indexes: all 6 present in sqlite_master after init
- FTS: quoted-token sanitize, hostile inputs raise nothing, symbol-only
  input returns [], real query still matches correct sermon
- Favorite: 0 FTS rebuilds on is_favorite/notes updates, exactly 1 on title
- UTC: created_at/updated_at delta < 5s in raw row; fresh llm row counted
  by get_llm_usage_summary(days=30); 40d-old llm row pruned
- Persistence: transcript absent from background_jobs.result JSON, small
  fields intact; executor trim verified
- Clear Completed removes completed+failed+cancelled, keeps queued/running
- prune_old_jobs: stale terminal row dropped from db+memory, recent kept,
  old queued kept
- Singleton: 8 concurrent get_job_queue threads -> one instance
- pytest tests/: 30 passed; ruff clean on all four files; CRLF preserved in
  job_queue.py and job_executors.py
