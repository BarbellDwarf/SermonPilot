# Upload an existing render

A render-only apply saves the approved cut locally and stops before the
SermonAudio API. The upload-only action publishes that same file later, using
the metadata already stored on the sermon row, without rendering again.

The action exists because the two approve buttons both re-render: "Approve ·
Render-only" and "Approve · Render+upload" run `process_new_sermon`, which can
re-run enhancement, cut detection and the encode. When the render already
exists, the operator wants the upload and nothing else.

## API surface

Upload-only is a mode of the existing apply endpoint, so the review page keeps
one write path:

```
POST /api/sermons/{sermon_id}/plan/apply
{
  "upload_only": true,
  "confirm_missing_description": false
}
```

`ApplyBody` carries the choice explicitly. `start` and `end` are ignored in
this mode, so they may be omitted.

A successful enqueue returns `202`:

```json
{
  "job_id": "…",
  "status": "queued",
  "render": { "name": "Teaching - Processed.mp4", "size": 734003200, "size_human": "700.0 MB" }
}
```

The job is a `sermon_publish` job with `upload_only: true` in its parameters.
Its label is `Upload existing render · <title> · <speaker>` and its description
is `Uploading the existing render for "<title>" (<speaker>).` The executor logs
the exact file name and human-readable size it used.

## What it reuses

The executor routes the stored render to the existing uploader,
`sermon_updater.publish_dry_run_sermon`, and passes the resolved file as
`upload_path`. That function creates the remote sermon, uploads the media,
publishes it, migrates the local row to the new SermonAudio id, and records the
upload. No new uploader is involved.

The resolved render is the `processed_file` pointer from the review metadata,
falling back to the sermon's stored audio file when the row is in a rendered
state or the filename marks it as a processed artifact. A source recording that
was never rendered is never treated as a render.

## Guards

The guards run in the API before a job exists, so the console gets an immediate
reason. The executor re-checks them, so a queued job that no longer qualifies
fails with the same message instead of rendering.

| `detail.code` | HTTP | When | Message |
|---------------|------|------|---------|
| `job_active` | 409 | A queued or running job already occupies the sermon | `an active job already exists for this sermon` |
| `already_published` | 409 | The sermon is `processed` or its `edit_status` is `uploaded` | `This teaching is already published on SermonAudio (<id>), so there is nothing to upload. Edit its details instead.` |
| `no_render` | 422 | No rendered output exists on disk | `No rendered output exists for this teaching, so there is nothing to upload. Render the approved cut first.` |
| `missing_description` | 422 | The description is empty and the confirmation flag is not set | `The description is empty, so uploading would publish a SermonAudio entry without one. Regenerate the description from the transcript, then upload. To upload without a description anyway, confirm it explicitly.` |
| `not_found` | 404 | No sermon row (the owner check normally returns 404 first) | `This teaching is not in the library, so there is nothing to upload.` |

A refusal never creates a job and never falls back to a full re-render.

## Empty description

`missing_description` carries `can_regenerate: true`. The console reacts by
opening a confirmation dialog that names the regeneration path and offers an
explicit "Upload anyway". Choosing it resends the request with
`confirm_missing_description: true`, which is the only way an entry is
published without a description.

## Console

The review page shows **Upload existing render** next to the approve actions on
wide viewports. On narrow viewports the primary Approve action stays pinned and
the action moves into the "More actions" overflow menu, alongside the other
secondary actions. It is enabled only when a rendered artifact is present and
hidden once the sermon is published. The refusal message is surfaced as a
toast, or as the confirmation dialog for an empty description.

## Tests

- `tests/unit/test_upload_only.py`: the router and executor use the stored
  render, skip the pipeline, and return each documented refusal.
- `tests/test_publish_dry_run.py`: the uploader uploads the explicit path and
  does not render.
- `tests/unit/test_job_labels.py`: the job states it is uploading the existing
  render.
- `web/src/components/SermonReview.test.tsx`: the console queues the upload,
  handles the empty-description confirmation, hides the action when published,
  and disables it when there is no render.
