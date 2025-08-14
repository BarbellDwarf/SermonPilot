# SermonAudio Updater

Automated sermon processing tool that enhances audio quality, generates AI summaries, and updates SermonAudio listings.

## Features

- **Audio Enhancement**:
  - AI-powered noise reduction
  - Audio amplification and normalization
  - Dynamic range compression
  - Support for both native Python processing and Audacity integration

- **AI-Powered Content Generation**:
  - Automatic sermon transcript summarization
  - Intelligent hashtag generation with verification system
  - Two-pass hashtag processing: generation + verification for clean output
  - Automatic removal of LLM comments and explanations from hashtags
  - Support for multiple LLM providers (Ollama, OpenAI, VaultAI)

- **SermonAudio Integration**:
  - Pull sermons by date, event type, or custom criteria
  - Update sermon descriptions and keywords
  - Upload processed audio files

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd sa-updater
```

Set up virtual environment:

### Using UV (Recommended)

```bash
# Install UV if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create venv with specific Python version
uv venv --python 3.11  # or 3.10, 3.12, etc.

# Activate the virtual environment
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies with UV
uv pip install -r requirements.txt
```

### Using standard venv

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Install Ollama (recommended):

```bash
# Windows
winget install Ollama.Ollama

# Mac
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh
```

Pull an LLM model:

```bash
ollama pull llama3
```

## Configuration

Copy the example configuration files:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```
Edit `config.yaml` or `.env` with your settings:
   - SermonAudio API key (get from your broadcaster dashboard)
   - Broadcaster ID
   - LLM provider settings
   - Audio processing preferences

## Usage

### Quick Start

List sermons from last 30 days (default window):
```bash
python sermon_updater.py --list-only
```

Process a single sermon by ID:
```bash
python sermon_updater.py --sermon-id 1234567890123
```

Process all Sunday AM sermons in last 14 days (dry run):
```bash
python sermon_updater.py --since-days 14 --event-type "Sunday - AM" --require-audio --dry-run
```

Process sermons in an explicit date range:
```bash
python sermon_updater.py --date-range 2024-01-01 2024-01-31 --auto-yes
```

Skip uploads (keep local files only):
```bash
python sermon_updater.py --sermon-id 1234567890123 --no-upload
```

Use alternate config:
```bash
python sermon_updater.py --config custom-config.yaml --list-only
```

Verbose / debug output:
```bash
python sermon_updater.py -v --sermon-id 1234567890123
```

### Core CLI Flags

| Flag | Purpose |
|------|---------|
| `--sermon-id ID` | Process exactly one sermon |
| `--list-only` | Only list matching sermons (no processing) |
| `--limit N` | Cap number of sermons to list/process |
| `--since-days N` | Filter sermons preached in last N days |
| `--date-range START END` | Filter by inclusive date range (YYYY-MM-DD) |
| `--year YYYY` | Convenience: process entire year (prompts) |
| `--no-upload` | Skip metadata + audio upload (still generates files) |
| `--dry-run` | Skip remote updates (implies --no-upload) |
| `--auto-yes` | Suppress confirmation prompts |
| `--config FILE` | Use alternate YAML config |
| `-v/--verbose` | Verbose debug logging |

### Sermon Filter Flags (map directly to SermonAudio API query params)

All of these are optional; combine as needed. Boolean flags set the underlying API parameter to true unless noted.

| CLI Flag | API Param | Description |
|----------|-----------|-------------|
| `--page` | `page` | Result page (default 1) |
| `--page-size` | `pageSize` | Page size (max 100) |
| `--exact-ref-match` | `exactRefMatch` | Exact Bible reference match |
| `--chapter` / `--chapter-end` | `chapter` / `chapterEnd` | Bible ref chapters |
| `--verse` / `--verse-end` | `verse` / `verseEnd` | Bible ref verses |
| `--featured` | `featured` | Featured only |
| `--search-keyword` | `searchKeyword` | Full-text search |
| `--include-transcripts` | `includeTranscripts` | Include transcript search (requires cache) |
| `--language-code` | `languageCode` | ISO 639 language code |
| `--require-audio` | `requireAudio` | Must have audio |
| `--require-video` | `requireVideo` | Must have video |
| `--require-pdf` | `requirePDF` | Must have PDF |
| `--no-media` | `noMedia` | Sermons with no media |
| `--series` | `series` | Series name (needs broadcaster) |
| `--denomination` | `denomination` | Broadcaster denomination |
| `--vacant-pulpit` | `vacantPulpit` | Vacant pulpit |
| `--state` | `state` | Broadcaster state/region |
| `--country` | `country` | ISO3 country |
| `--speaker-name` | `speakerName` | Speaker name |
| `--speaker-id` | `speakerID` | Speaker numeric ID |
| `--staff-pick` | `staffPick` | Staff pick |
| `--listener-recommended` | `listenerRecommended` | Listener recommended |
| `--preached-year` | `year` | Year preached (filter) |
| `--month` | `month` | Month (1-12) |
| `--day` | `day` | Day (1-31) |
| `--audio-min-duration` | `audioMinDurationSeconds` | Min audio duration (s) |
| `--audio-max-duration` | `audioMaxDurationSeconds` | Max audio duration (s) |
| `--lite` | `lite` | Lite sermons mode |
| `--lite-broadcaster` | `liteBroadcaster` | Lite broadcaster mode |
| `--cache` | `cache` | Enable API caching |
| `--preached-after` | `preachedAfterTimestamp` | UNIX seconds after |
| `--preached-before` | `preachedBeforeTimestamp` | UNIX seconds before |
| `--collection-id` | `collectionID` | Collection ID |
| `--include-drafts` | `includeDrafts` | Include drafts |
| `--include-scheduled` | `includeScheduled` | Include scheduled |
| `--exclude-published` | `includePublished=false` | Exclude published (negated) |
| `--book` | `book` | OSIS book code |
| `--sermon-ids` | `sermonIDs` | Comma-separated sermon IDs |
| `--event-type` | `eventType` | Event type string |
| `--broadcaster-id` | `broadcasterID` | Override broadcaster |
| `--sort-by` | `sortBy` | Sort field |

Tip: If you only need a quick list, add `--list-only` to avoid processing overhead.

## Audio Processing Options

### Native Python Processing (Default)

The script uses Python libraries for audio processing:
- `noisereduce` - AI-based noise reduction
- `pydub` - Audio manipulation and effects
- `scipy` - Signal processing

### Audacity Integration (Optional)

To use Audacity for processing:

1. Install Audacity
2. Enable mod-script-pipe:
   - Edit > Preferences > Modules
   - Set "mod-script-pipe" to "Enabled"
   - Restart Audacity

3. Create a macro named "Sermon Edit" with your desired effects

4. Set `use_audacity: true` in config.yaml

## LLM Configuration

### Hashtag Verification

The system uses a two-pass approach for reliable hashtag generation:

1. **Generation Pass**: LLM generates initial hashtags based on sermon content
2. **Verification Pass**: Second LLM call cleans and verifies hashtags

This removes common issues like:
- Comments and explanations mixed with hashtags
- Non-hashtag content in the output
- Inconsistent formatting

Configure in `config.yaml`:
```yaml
hashtag_verification: true  # Enable two-pass verification (default)
# Set to false for single-pass generation (legacy behavior)
```

### Ollama (Recommended)

1. Install Ollama (see Installation)
2. Pull a model: `ollama pull llama3`
3. Set `llm_provider: ollama` in config

### OpenAI

1. Get API key from OpenAI
2. Set `llm_provider: openai` and add your API key

### VaultAI

SermonAudio's AI service (when available)

## Troubleshooting

### "Ollama not available"
- Make sure Ollama is running: `ollama serve`
- Check if model is installed: `ollama list`

### "No audio URL found"
- Verify the sermon has audio uploaded
- Check API permissions

### Audio processing issues
- Install ffmpeg for better format support
- Check file permissions

## Examples

### Examples

Process five most recent staff picks with audio:

```bash
python sermon_updater.py --staff-pick --require-audio --limit 5 --list-only
```

Generate summary + hashtags for a sermon but don't upload:

```bash
python sermon_updater.py --sermon-id 1234567890123 --no-upload
```

Filter by speaker and series in March 2024:

```bash
python sermon_updater.py --speaker-name "John Smith" --series "Romans" --date-range 2024-03-01 2024-03-31 --list-only
```

Advanced: only sermons missing media (triage backlog):

```bash
python sermon_updater.py --no-media --since-days 90 --list-only
```

## API Rate Limits

- SermonAudio: Check your broadcaster plan
- Ollama: No limits (local)
- OpenAI: Based on your plan

## Contributing

Pull requests welcome! Please:
- Follow PEP 8 style guidelines
- Add tests for new features
- Update documentation

## License

MIT License - see LICENSE file

## Support

- SermonAudio API docs: https://api.sermonaudio.com
- Issues: GitHub Issues
- SermonAudio support: support@sermonaudio.com
