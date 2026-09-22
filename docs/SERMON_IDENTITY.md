# Sermon identity

Every sermon lives in one row of the `sermons` table, keyed by an id derived
from the sermon's own attributes and its source media. Processing the same
recording again updates that row. A different recording resolves to a different
row. The database never holds two rows for one sermon.

## The identity

Identity is the triple of normalised speaker, recorded date and title, plus a
fingerprint of the source media.

| Part | Column | Normalisation |
|---|---|---|
| Speaker | `speaker` | lowercase, runs of non-alphanumeric characters to `_`, empty to `unknown` |
| Date | `recorded_date` | digits only, empty to `nodate` |
| Title | `title` | same as speaker, empty to `untitled` |
| Fingerprint | source media | described below |

`src/sermon_identity.py::derive_sermon_id` builds the id:

```
draft_<speaker[:20]>_<date[:8]>_<title[:40]>_<digest[:12]>
```

The readable prefix keeps ids searchable in logs and in the Library. The
trailing `digest` is the first 12 hex characters of
`sha256(speaker|date|title|fingerprint)`, computed over the **full** normalised
values. Two sermons whose full titles share the first 40 characters produce
different digests, because the digest input is the untruncated title. The
prefix can repeat; the digest separates the rows.

Ids are URL-safe. The output alphabet is lowercase letters, digits and
underscores, which fits a path segment and a JSON key without escaping.

## Source fingerprint

The fingerprint ties the id to the media itself where the media can be read.

| Situation | Fingerprint |
|---|---|
| Local file readable | `local:<sha256(size + head 1 MiB + tail 1 MiB)>` |
| Local file unreadable | `path:<name>:<size>` |
| Remote reference with size | `remote:<name>:<size>` |
| Name and size only | `name:<name>:<size>` |
| No source | empty string |

The local hash samples the size plus the first and last mebibyte. Re-staging a
byte-identical file under a new temporary name yields the same digest, so the
second staging updates the first record. Sampling is a deliberate trade: full
hashing of a multi-gigabyte recording on every request would cost more than the
duplicate it prevents, and the size plus both ends make an accidental match
between two different recordings impractical.

## Creation paths

Every path that creates a record now computes the same id, and every path that
re-renders an existing record carries that record's id through.

| Entry point | Module | Id source |
|---|---|---|
| Interactive auto-edit review pause | `sermon_updater.py::process_new_sermon` | carried id, else derived from speaker/date/title and source |
| Normal processing and dry run | `sermon_updater.py::process_new_sermon` | carried id, else derived |
| Recovery draft after a failed run | `sermon_updater.py::process_new_sermon` | carried id, else derived |
| Browser upload draft | `server/api/routers/writes.py` | derived, with a fingerprint of the written file |
| Server-path draft | `server/api/routers/writes.py` | derived, with a fingerprint of the source path or remote reference |
| Console new draft | `server/api/routers/sermons.py` | derived from speaker/date/title |
| Render and refine continuation | `ui/auto_edit_apply.py::run_library_apply` | the sermon's existing id |
| Processing job | `ui/job_executors.py` | `sermon_id` from the job parameters |

`process_new_sermon` accepts `existing_sermon_id`. Jobs set it from the job
parameters, and apply continuation jobs set it from the sermon being edited.
`_resolve_identity_id` returns that id when present and derives one otherwise,
so CLI and Streamlit callers keep working without a carried id.

`SermonRepository.save_sermon` upserts on the primary key. It refreshes the
sermon columns and leaves `edit_plans`, `notes` and `sermon_content` alone, so a
re-run keeps its history, plans and annotations.

## Duplicate migration

Existing databases can hold two or more rows for one sermon, usually one row
per processing attempt. `SermonRepository.dedupe_sermons` folds them at
startup.

The hook runs at the end of `SermonDatabase.init_database`. The read-only
database subclass does not run `init_database`, so a read-only connection never
writes.

The migration groups rows by `identity_key`, which is speaker, date and title
without the source fingerprint. Source-independent grouping means a draft
created from a re-staged file still folds into its earlier row.

For each group with more than one member:

1. **Skip groups with distinct remote ids.** When two rows point at two
   different non-empty `upload_info.sermonaudio_id` values, the group is left
   alone and the skip is logged. Two published SermonAudio sermons are never
   merged.
2. **Score each row** in `_identity_score`: media that exists on disk first,
   then a remote id, then `processed` or `draft` status, then the highest edit
   plan revision, then transcript length, then notes. The survivor is the
   highest score, with ties broken by revision, then the newest `updated_at`,
   then the id.
3. **Fold each loser** into the survivor in `_fold_sermon`: file rows (only
   for file types the survivor has no path for, so a recorded path is never
   replaced by a loser's path), content fields (the longest value per field),
   processing info, upload info, notes (appended when unique), the `user_id`
   when the survivor has none, and edit plans. Loser plans are renumbered
   above the survivor's highest revision, and older revisions are marked
   `superseded`. When a folded row was `processed`, the survivor is promoted
   to `processed` so a published sermon is never downgraded to a draft.
4. **Delete the loser rows** from every child table and the main table, then
   rebuild the search row.

Each merge logs the kept id, the identity key, the survivor's media file count,
its highest revision, its remote id and the removed id. The group count and the
kept/removed pairs are returned in the summary.

The migration is idempotent by construction. A second run finds no group with
two members and reports zero merges. Running it against an already collapsed
database changes nothing.

## Concurrency and user ownership

Identity ignores `user_id`. Two users who submit the same sermon attributes and
source resolve to one row, which matches the one-sermon-one-record rule. The
first creator keeps ownership: `save_sermon` sets `user_id` only when the
column is NULL, and the migration copies a loser's `user_id` only when the
survivor has none.

## Limits

The fingerprint depends on the source attributes available at creation time. A
pure CLI dry run that generates its title from the LLM produces a new title
each run, and the title is part of identity, so those runs derive different ids.
Jobs, the console and the API pass a resolved title and reuse the carried id,
so they do not have this problem. Treat a repeated pure CLI dry run with a
generated title as a new draft.
