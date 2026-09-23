# Cancellation

Cancelling a job stops the work it is doing. The single worker is released
within seconds, whatever stage the job reached, and the job ends in a terminal
state instead of sitting at `running`.

## The hook

Jobs are cancelled cooperatively. `JobQueue.cancel_job` sets `job.cancelled`
and flips the row to `cancelled`, and the running executor observes that flag
through a cancel hook:

- `ui/job_executors.py::_raise_if_job_cancelled(job)` is the hook at the queue
  edge. It raises `JobCancelledError` when the job is cancelled.
- `process_new_sermon` wraps the hook in `_check_cancelled`, which converts any
  exception the hook raises into `ProcessingCancelledError`. Every
  `progress_callback` call is also a checkpoint, so progress-reporting stages
  poll the hook at their own cadence.

A hook is only useful if the code holding the worker gets a chance to run it.
A blocking `subprocess.run` does not: it returns when the child exits, however
long that takes. That gap is what left an ffmpeg encode running after its job
was cancelled.

## Supervised children

`src/supervised_process.py::run_supervised` is the supported way to run an
external command from a cancellable stage. It starts the child with
`subprocess.Popen`, polls the cancel hook every `poll_interval` seconds
(default 2), and on cancel:

1. logs `Cancel requested - stopping <step>`,
2. sends `SIGTERM` to the child's process group (the child runs in its own
   session, so grandchildren a shell wrapper left behind are signalled too),
3. waits `terminate_grace` seconds (default 10), then sends `SIGKILL` and
   reports the escalation in the log,
4. moves every path in `partial_paths` into the trash area through
   `src/safe_delete.py::trash_local`, never an unlink,
5. logs `Cancelled during <step> (stopped after Ns)`,
6. raises `ProcessCancelled`.

Without a `cancel_check` the function defers to `subprocess.run`, so CLI runs
and one-shot renders keep their existing behaviour and timeout semantics.

When the cancel hook fires, the child always gets a fresh poll check before the
first progress report, so the current-step cancel lines are never overwritten by
a stale stage message.

## Converted call sites

| Stage | Call site |
|---|---|
| Keeper transcode | `src/auto_edit.py::transcode_to_keeper` |
| Edit render | `src/auto_edit.py::apply_edit` via `_run_ffmpeg` |
| Snippet shift | `src/auto_edit.py::shift_snippet_audio` |
| Review snippets | `src/auto_edit.py::_render_snippet` |
| Audio extraction from video | `sermon_updater.py::process_new_sermon` |
| Audio transcode back to input format | `sermon_updater.py::_transcode_media` |
| Video mux | `sermon_updater.py::process_new_sermon` |
| clean-audio.py preprocessing | `sermon_updater.py::process_new_sermon` |
| A/V frame extraction and waveform probe | `src/av_sync.py::_extract_frames`, `_audio_envelope`, `measure_waveform_offset` |

Cloud transfers already polled the hook while their child ran, and now report
the same two log lines: `ui/job_executors.py::_rclone_copyto` for downloads and
`_upload_cloud_output` for uploads. A staged download left incomplete by a
cancel is moved into trash instead of unlinked.

Audio enhancement (`AudioProcessor.process_sermon_audio`) and transcription are
native library calls rather than child processes. They are polled immediately
before and after, and transcription polls once per decoded segment; the
worst-case delay for those two stages is the length of the single native call.

## Partial output

A cancelled render's partial file is named in `partial_paths` and moves into
the trash root with `reason="cancelled_render_partial"`. The render output is
recorded only after the render returns, and the cancellation is raised before
that point, so no local record points at a file the job did not finish. On the
retry path the partial is rebuilt rather than reused.

## Boundary

A retried job re-processes its uploaded copy. `_cleanup_job_files` keeps the
uploaded file on a cancel so the retry has a source, and moves only the derived
`_enhanced` and `_cleaned` siblings into trash.

## Restart reconciliation

A cancel needs a live worker to signal. A container recreate (deploy, crash,
manual recreate) kills the worker thread, which is a daemon, while its
`background_jobs` row stays at `running`. The row then blocks a new job for the
same sermon, and `POST /api/jobs/<id>/cancel` has nothing to signal, so it
answers `{"cancelled": false}`.

Startup reconciliation is the backstop for that case. Every process that loads
the job store finds rows in an in-flight state (`running` or `paused`, never
`queued`: a fresh worker can claim a queued row) and marks them terminal:

- status `failed`, or `cancelled` when the row's cancel flag was already set;
- `completed_at` set to the reconciliation time;
- a `Job interrupted by app restart` line appended to the existing log, which is
  never wiped;
- the result replaced with an interruption outcome. It carries no output paths,
  so a partially written file is not registered as finished work. Completed
  artifacts are left where they are.

`ui/job_queue.py::reconcile_interrupted_jobs` performs this against the store
directly. The queue loader calls it through `_recover_orphaned_jobs`, and the
API startup hook calls it so the console sees the terminal row before the first
request, not only after some later write. Both paths write the same fields, and
the operation is idempotent: a second run finds no in-flight rows and changes
nothing, so the two processes cannot disagree.

The write-path guard (`server/api/routers/writes.py::_active_job_for`) skips a
restart-reconciled row in its `_ACTIVE_JOB_GRACE_SECONDS` window. That window
exists to catch a double-click behind a job that completed on its own; an
interrupted job did not complete behind the click, so it must not block the
next apply.

Reconciliation assumes the process that owns the store has restarted, so no
worker anywhere can still be running those rows. It is not a liveness protocol
for two processes sharing a database while both are up.

