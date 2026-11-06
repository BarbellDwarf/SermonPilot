# Replace a published recording

Use this when the media on an existing SermonAudio entry is wrong and a better source exists. The entry, its title, description, hashtags, series, and publication state stay the same.

## From the console

1. Open the published teaching in the library.
2. Open **More actions** and choose **Replace recording**.
3. Pick the new video or audio file.
4. Choose **Replace and reprocess**.

The job appears on the Jobs page, like any other processing run.

## What the pipeline does

The new file goes through the normal path:

- transcription
- audio enhancement and noise suppression
- keeper transcode when the source is large
- automatic opening and closing cuts
- metadata reuse
- upload to the existing SermonAudio id

Automatic cuts apply when detection is confident. If it is not, the replacement publishes the full recording rather than stalling in review. The old cut plan is superseded either way.

## Local files

The previous `- Original` file moves to the configured trash directory through `src/safe_delete.py`. The new upload becomes the retained original, so a later edit or restore starts from the new source.

The previous cut plan is superseded when the replacement produces no new plan. That prevents the review screen from applying cuts that describe the retired recording.

## Requirements

- The sermon must be processed.
- It must already have a SermonAudio id.
- The requesting user must own the sermon and have a connected SermonAudio account.
- No other job may be active for the sermon.
