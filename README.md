# SermonAudio Processor

Automated sermon processing tool that enhances audio quality, generates AI summaries, updates SermonAudio listings, and provides comprehensive analytics with AI-powered insights.

## Features

- **Complete Sermon Workflow**:
  - **Create new sermons** from audio files with AI-generated metadata
  - **Update existing sermons** with enhanced audio and improved descriptions
  - **Metadata-only processing** for quick content updates
  - **Validation and regeneration** of sermon descriptions

- **Audio Enhancement**:
  - AI-powered noise reduction (DeepFilterNet, Resemble Enhance)
  - Audio amplification and normalization
  - Dynamic range compression
  - Support for both native Python processing and Audacity integration

- **AI-Powered Content Generation**:
  - **Audio transcription** using OpenAI Whisper (multiple model sizes)
  - Automatic sermon transcript summarization
  - Intelligent hashtag generation with verification system
  - Two-pass hashtag processing: generation + verification for clean output
  - Automatic removal of LLM comments and explanations from hashtags
  - Support for multiple LLM providers (Ollama, OpenAI, VaultAI)

- **📈 Advanced Analytics & Insights**:
  - **Real-time Performance Monitoring**: CPU, memory, GPU usage tracking
  - **Processing Metrics**: Success rates, processing times, error analysis
  - **SermonAudio Analytics**: Views, listens, downloads, engagement tracking
  - **🤖 AI-Powered Chat Interface**: Natural language queries about your sermon data
  - **RAG System**: Vector search and retrieval for sermon insights
  - **Cost Tracking**: LLM API usage and optimization recommendations

- **🖥️ Modern Web Interface**:
  - **Streamlit Web UI** for intuitive interaction
  - **Dashboard** with recent activity and system status
  - **Batch Processing** with advanced filtering and progress tracking
  - **Analytics Visualizations** with interactive charts
  - **Configuration Management** with web-based editing

- **SermonAudio Integration**:
  - Pull sermons by date, event type, or custom criteria
  - Update sermon descriptions and keywords
  - Upload processed audio files
  - Create new sermons directly from audio files

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd sermon-ai-audio-processor
```

### Quick Install (Recommended)

For most users, use UV for fast dependency management:

```bash
# Install UV if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/Mac
# or download from https://github.com/astral-sh/uv for Windows

# Create venv with specific Python version
uv venv --python 3.11

# Activate the virtual environment
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Install all dependencies
uv pip install -r requirements/requirements.txt
```

### Platform-Specific Installation

#### Linux with GPU Support
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt update && sudo apt install -y ffmpeg libsndfile1 portaudio19-dev python3-dev

# Install with CUDA support (note: requires --index-strategy flag for dependency resolution)
uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
```

#### CPU-Only (Any Platform)
```bash
# For systems without GPU or for testing
uv pip install -r requirements/requirements-cpu.txt
```

#### Development Setup
```bash
# Install all dependencies including optional AI models
uv pip install -r requirements/requirements-dev.txt
```

### Standard pip Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Choose your installation:
pip install -r requirements/requirements.txt         # Standard installation
pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match   # Linux with GPU support  
pip install -r requirements/requirements-cpu.txt     # CPU-only
pip install -r requirements/requirements-dev.txt     # Development
```

### Verify Installation

```bash
# Test core functionality
python -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
python -c "import df; print('DeepFilterNet (df): OK')"

# Test resemble-enhance (if installed separately)
python -c "import resemble_enhance; print('Resemble Enhance: OK')" 2>/dev/null || echo "Resemble Enhance: Not installed (install manually)"
```

### Enhanced AI Models

For the highest quality audio enhancement, install additional AI models:

```bash
# Install Resemble Enhance (best quality, complex installation)
pip install resemble-enhance

# Other optional models
pip install voicefixer speechbrain demucs
```

**Note**: Some AI models have complex dependencies. See our detailed installation guides:
- [Linux Installation Guide](docs/LINUX_INSTALLATION.md)
- [AI Models Installation Guide](docs/AI_MODELS_INSTALLATION.md)

For detailed Linux installation instructions, see [docs/LINUX_INSTALLATION.md](docs/LINUX_INSTALLATION.md).

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
   - Analytics settings (optional)

### Web Interface Dependencies

For the modern web interface and analytics features, install additional UI dependencies:

```bash
# Install Streamlit and analytics dependencies
pip install streamlit plotly chromadb sentence-transformers pandas psutil

# Or use the included UI requirements file
pip install -r ui/requirements-ui.txt
```

## Usage

### Web Interface (Recommended)

Launch the modern web interface for intuitive interaction:

```bash
# Start the Streamlit web interface
streamlit run streamlit_app.py

# Open your browser to http://localhost:8501
```

The web interface provides:
- **📊 Dashboard**: Recent activity and system status
- **🎵 New Sermon**: Upload and process individual sermons
- **🔄 Batch Processing**: Process multiple sermons with filtering
- **✅ Validation**: Quality control and description regeneration
- **📈 Analytics**: Performance metrics and SermonAudio insights
- **🤖 AI Chat**: Natural language queries about your sermon data
- **⚙️ Settings**: Configuration management

### Command Line Interface

For automation and scripting, use the CLI:

### Linux Server Scripts

For Linux users, we provide convenient server management scripts:

#### Simple Startup (Interactive)
```bash
# Start the Streamlit web interface
./start_server.sh
```
This script will:
- ✅ Check and activate your virtual environment
- ✅ Verify all dependencies are installed
- ✅ Start the Streamlit server on http://localhost:8501
- 🎯 Run interactively (Ctrl+C to stop)

#### Advanced Server Manager
```bash
# Start the server in background
./server.sh start

# Check server status
./server.sh status

# Stop the server
./server.sh stop

# Restart the server
./server.sh restart

# View server logs
./server.sh logs
```

#### Windows
```bash
# For Windows users
start_server.bat
# OR
python start_server.py
```

### Manual Server Start
```bash
# Activate your environment first
source .venv/bin/activate  # Linux/Mac
# OR .venv\Scripts\activate  # Windows

# Start Streamlit manually
streamlit run streamlit_app.py --server.port 8501
```

## Usage

### Creating New Sermons from Audio Files

Create a new sermon with AI-generated metadata:
```bash
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15"
```

With Bible reference for better content generation:
```bash
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15" --bible-text "John 3:16"
```

Fast processing without transcription:
```bash
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15" --skip-transcription
```

Test what would be created (dry run):
```bash
python sermon_updater.py --dry-run new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15"
```

### Processing Existing Sermons

List sermons from last 30 days (default window):
```bash
python sermon_updater.py list
```

Process a single sermon by ID:
```bash
python sermon_updater.py sermon-update --sermon-id 1234567890123
```

Process all Sunday AM sermons in last 14 days (dry run):
```bash
python sermon_updater.py sermon-update --since-days 14 --event-type "Sunday - AM" --require-audio --dry-run
```

Update only metadata (skip audio processing):
```bash
python sermon_updater.py metadata-update --speaker-name "Pastor Smith" --since-days 7
```

### Validation and Quality Control

Validate sermon descriptions:
```bash
python sermon_updater.py validation --validate-descriptions --limit 10
```

### Additional Examples

Process sermons in an explicit date range:
```bash
python sermon_updater.py sermon-update --date-range 2024-01-01 2024-01-31 --auto-yes
```

Skip uploads (keep local files only):
```bash
python sermon_updater.py sermon-update --sermon-id 1234567890123 --no-upload
```

Use alternate config:
```bash
python sermon_updater.py --config custom-config.yaml list
```

Verbose / debug output:
```bash
python sermon_updater.py -v sermon-update --sermon-id 1234567890123
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
