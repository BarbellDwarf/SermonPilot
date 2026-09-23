# Deletion policy

Every media deletion in SermonPilot is a move into a recoverable location. A
local file goes to a dated trash area. A cloud object stays on its remote, and
when a remote change is genuinely required it moves into a dated trash prefix on
that same remote. Nothing under the policy is unlinked, and no cloud object is
destroyed as a side effect of dropping a database row.

`src/safe_delete.py` holds the policy. Every delete path calls into it, so the
rules live in one module instead of at each call site.

## The rule

A delete that can be undone is a move. `trash_local` moves a file or directory
into the trash root and writes a record beside it. `trash_remote` issues one
`rclone moveto` into a `_trash/<date>/` prefix on the same remote. Neither path
removes an original outright.

The only permanent removal in the product is `sweep_trash`, which deletes trash
items older than the retention window. It never touches media outside the trash
root.

## Local trash layout

```
<data>/_trash/<YYYY-MM-DD>/<epoch-ms>-<token>/<original-name>
<data>/_trash/<YYYY-MM-DD>/<epoch-ms>-<token>/trash_record.json
```

The `<data>` root resolves in order: `SERMONPILOT_TRASH_DIR`, the
`trash_directory` config value, then `default_cache_root()/_trash`. A relative
configured path is anchored at the project root.

Each move lands in its own `<epoch-ms>-<token>` directory so two files with the
same basename never collide, and the original name is preserved. A delete is
reported with the source and the destination, so the UI and API responses point
at the trash location instead of claiming a permanent removal.

### Trash record

Every move writes `trash_record.json` beside the moved item. It carries:

| Field | Meaning |
|---|---|
| `source` | where the item was |
| `destination` | where it went |
| `mode` | `local`, `remote`, or `remote-kept` |
| `reason` | why it moved, for example `sermon_deleted` |
| `deleted_at` | when |
| `sermon_id`, `job_id`, `stage` | what it belonged to |
| `moved` | false when the item was left in place, by policy or after a failed move |
| `recoverable` | what the caller records in its response |

A failed move leaves the source alone and returns a record with `moved` false.
The record is the audit trail for a restore.

## Retention and sweep

Trash is bounded. `sweep_trash` removes items older than the retention window,
which defaults to 30 days. A window of zero or less disables the sweep, so trash
is never cleared unless the operator has set a window.

`SERMONPILOT_TRASH_RETENTION_DAYS` overrides the window, and the
`trash_retention_days` config key is the saved equivalent. The sweep runs once
at Streamlit startup through `ui/config_utils.py::sweep_stale_job_files`, which
already handles the job temp roots. Item age is read from the item directory's
mtime, and the sweep is idempotent: a second run finds nothing past the window.

## Cloud media

A cloud reference has the form `remote:<name>:<sub>`. Two functions act on it.

`keep_remote_media` records that the object is left in place and reports it as
recoverable at its original reference. Library deletes use this mode, because
dropping a row is not a reason to destroy the media in a mount.

`trash_remote` moves the object with `rclone moveto` into
`<name>:_trash/<date>/<basename>` on the same remote. It is the supported way to
make a genuine remote change.

Both functions avoid destructive rclone operations. `rclone purge` is never
issued, and `--drive-use-trash=false` is never passed, so the provider's own
trash semantics stay intact. Logs redact the cloud sub-path and keep only the
remote name and the basename, because the folder trail can identify a church.

## Where deletes happen

| Call site | Module | Action |
|---|---|---|
| Review snippets and staged files | `src/review_media.py` | move to local trash |
| Job temp files and staging dirs | `ui/job_executors.py` | move to local trash |
| Replaced original after auto-edit | `src/auto_edit.py::trash_original_after_edit` | move to local trash |
| Partial output of a cancelled child process | `src/supervised_process.py` | move to local trash |
| Incomplete staged cloud download after cancel | `ui/job_executors.py::_trash_partial_download` | move to local trash |
| Dry-run old output directory | `sermon_updater.py` | move to local trash |
| Library single and batch delete | `ui/ui_pages/library.py` | move local media, keep cloud |
| Library delete API | `server/api/routers/sermons.py` | move local media, keep cloud |

`should_delete_original` stays a predicate. `trash_original_after_edit` is the
only supported action on it, so a retained original is never unlinked while a
re-edit is still possible.

## Restore

Local media restore is a move back out of the trash directory. Find the item by
its `trash_record.json` `source` field, then move the file from `destination`
back to `source`. Sweeping is the only step that makes this impossible, so an
item inside the retention window can always be recovered.

Cloud media is recoverable through the provider. A `remote-kept` object was
never touched. A `remote` object sits under `_trash/<date>/` on the same remote
and can be moved back with `rclone moveto`.

## What is still removed

Two kinds of artifact stay on the existing unlink or rmtree path, because losing
them is not a media loss:

- Job processing directories and partial failed downloads, which are rebuilt on
  the next run.
- Temporary plan files and API caches, which hold no sermon media.

Config backup rotation in `src/config_management/backup_manager.py` sits outside
the media scope of this policy.

## Boundaries

Re-rendering writes over its own output file in place. The policy covers delete
operations, so replacing a previous render is not routed through the trash root.
A re-edit that supersedes a retained original is not an in-place overwrite:
`trash_original_after_edit` moves the original into trash before the edited
result takes its place.
