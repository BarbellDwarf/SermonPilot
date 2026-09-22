# Analytics

## Overview

The Streamlit web UI includes an Analytics page (`ui/ui_pages/analytics.py`)
that reports on sermon processing from the local SQLite database and fetches
engagement data from the SermonAudio API.

## Enabling Analytics

Analytics is always available: the page renders whenever the Streamlit UI runs,
with no configuration gate.

The data comes from two places:

- The local `sermons` table (processing dates, speakers, event types, titles)
- The SermonAudio API (downloads, video downloads, comment counts, and
  recent-access timestamps for your broadcaster's sermons)

## The Analytics Page

Open the Streamlit UI and navigate to the Analytics page. It has five tabs:

| Tab | Contents |
|-----|----------|
| Processing Metrics | Sermons processed per time range, success rate, error types, processing time trend |
| Content Analysis | Speaker and event-type distribution from the local database |
| Cost Tracking | LLM API call counts, token usage, and estimated cost per month |
| Performance | Live CPU, memory, disk, network, and GPU metrics via `ui/performance_monitor.py` |
| SermonAudio Analytics | A data view of API engagement metrics |

### SermonAudio Analytics Data View

The data view lists sermons with the metrics the SermonAudio API actually
provides:

- Downloads and video downloads
- Comment count
- Audio/video duration
- Last audio/video access timestamps (used as a "recent activity" signal)

The API does not expose view or listen counts to regular accounts, so the
`views` field is reported as 0. When no API credentials are configured, or
the fetch fails, the client falls back to mock/demo data and the page shows a
warning.

## Troubleshooting

**Analytics data not loading:** use the "Refresh Data" button on the Processing
Metrics tab to clear the cached data.

**SermonAudio engagement metrics missing or zero:** the API does not provide
play/view counts for regular accounts, so views are always 0. Downloads,
comment counts, and access timestamps are the real signals available.

## Performance Monitoring

The Performance tab reads system metrics from `ui/performance_monitor.py`:
CPU usage, memory usage, disk usage, network I/O, and NVIDIA GPU utilization
and memory when a GPU is present.
