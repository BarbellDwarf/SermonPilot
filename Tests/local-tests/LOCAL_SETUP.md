# Local Testing Setup Guide

## Prerequisites

This guide explains how to set up a complete local testing environment for the SermonAudio Processor.

### Required Dependencies

- **Python 3.11+** with UV package manager
- **CUDA-capable GPU** (optional, for AI audio processing)
- **Valid SermonAudio API credentials**
- **External services**: Ollama server
- **ChromaDB dependencies**

## Quick Setup

### 1. Python Environment Setup

```bash
# Install UV package manager if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install dependencies
uv pip install -r requirements.txt
uv pip install -r ui/requirements-ui.txt
```

### 2. External Services Setup

#### Ollama (Local LLM)
```bash
# Install Ollama (see https://ollama.ai for platform-specific instructions)
# Linux/Mac:
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# In another terminal, pull required models
ollama pull llama3.1:8b
ollama pull gemma2:2b  # Smaller model for validation

# Verify models are available
ollama list
```

### 3. Configuration Setup

```bash
# Copy example configuration
cp config.example.yaml config.yaml

# Edit config.yaml with your credentials
# Required fields:
# - api_key: Your SermonAudio API key
# - broadcaster_id: Your SermonAudio broadcaster ID
# - Optionally configure OpenAI or other LLM providers
```

### 4. Verify Environment

```bash
# Run environment check
python Tests/local-tests/environment-check.py

# Expected output: "Environment ready for full testing"
```

## Test Execution

### Environment Verification
```bash
# Check all dependencies and services
python Tests/local-tests/environment-check.py
```

### UI Testing
```bash
# Start Streamlit for manual testing
streamlit run ui/streamlit_app.py
# Access at http://localhost:8501
```

### Integration Tests
```bash
# Run local integration test suite
python Tests/local-tests/test-runner.py

# Run specific test categories
python Tests/local-tests/api-integration-tests.py
python Tests/local-tests/ui-functionality-tests.py
python Tests/local-tests/audio-processing-tests.py
python Tests/local-tests/rag-system-tests.py
```

## Testing Capabilities by Environment

### Local Environment (Full Capabilities)
- ✅ **Live SermonAudio API Integration**: Real API calls, data fetching, uploads
- ✅ **LLM Provider Testing**: OpenAI, Ollama, multi-provider fallback
- ✅ **Audio Processing Pipeline**: AI enhancement, GPU/CPU processing
- ✅ **ChromaDB/RAG System**: Vector embeddings, semantic search
- ✅ **Streamlit UI Execution**: Full interactive web interface
- ✅ **Performance Monitoring**: Real-time system metrics
- ✅ **End-to-end Integration**: Complete workflow testing

### Cloud Environment (Limited)
- ✅ **Static Code Analysis**: AST parsing, syntax validation, import analysis
- ✅ **Configuration Validation**: YAML schema validation, config structure checks
- ✅ **Mock Data Detection**: Pattern scanning for hardcoded test data
- ❌ **No External API Calls**: Cannot connect to SermonAudio API, OpenAI, etc.
- ❌ **No Local Services**: Cannot run Ollama, databases, or local servers
- ❌ **No Interactive UI Testing**: Cannot launch Streamlit server

## Test Categories

### 1. API Integration Tests
**File**: `Tests/local-tests/api-integration-tests.py`
- SermonAudio API connectivity
- LLM provider responses  
- Rate limiting compliance
- Error handling validation

### 2. UI Functional Tests
**File**: `Tests/local-tests/ui-functionality-tests.py`
- Streamlit page rendering
- Form submission workflows
- Navigation and routing
- Interactive component behavior

### 3. Audio Processing Tests
**File**: `Tests/local-tests/audio-processing-tests.py`
- AI model loading and execution
- Audio enhancement pipelines
- GPU/CPU fallback mechanisms
- File processing workflows

### 4. RAG System Tests
**File**: `Tests/local-tests/rag-system-tests.py`
- Vector database operations
- Semantic search functionality
- Natural language query processing
- Embedding generation

## Troubleshooting

### Common Issues

#### "Ollama not accessible"
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# If not running, start Ollama service
ollama serve

# Verify models are available
ollama list
```

#### "Missing required packages"
```bash
# Reinstall dependencies
uv pip install -r requirements.txt
uv pip install -r ui/requirements-ui.txt

# For AI audio processing (optional)
uv pip install resemble-enhance voicefixer speechbrain
```

#### "CUDA not available"
```bash
# Check PyTorch CUDA installation
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"

# If False, reinstall PyTorch with CUDA support
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

#### "config.yaml invalid"
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check required fields are present
python Tests/cloud-tests/config-validation.py
```

### Debug Mode

Enable debug mode for verbose output:

```yaml
# config.yaml
debug: true
```

### Performance Considerations

- **Large audio files**: Automatic chunking based on available memory
- **Model initialization**: Cached after first load, device-aware placement
- **API rate limits**: Built-in throttling for SermonAudio calls
- **Memory management**: Monitor usage with `psutil`, clean up models between runs

## Safety Guidelines

### Local Environment
- ⚠️ **Verify credentials before testing**: Check API keys and service availability
- ⚠️ **Monitor resource usage**: Audio processing can be resource-intensive
- ⚠️ **Respect rate limits**: SermonAudio API has usage restrictions
- ⚠️ **Backup configurations**: Create backups before modifying config files

### Test Data
- Use test sermons for development
- Avoid processing production sermons during testing
- Clean up test artifacts after testing

## Success Criteria

### Local Environment Validation
- [ ] Streamlit UI launches and functions correctly
- [ ] All external integrations working (APIs, Ollama, etc.)
- [ ] Audio processing pipeline operational
- [ ] RAG system performing semantic queries
- [ ] Performance monitoring displaying real metrics
- [ ] No mock data in production code paths

## Next Steps

After successful local setup:

1. **Manual UI Testing**: Launch Streamlit and test all features
2. **Integration Testing**: Run automated test suite
3. **Performance Testing**: Monitor resource usage during processing
4. **API Testing**: Verify SermonAudio integration with real data
5. **End-to-end Testing**: Complete workflow from upload to processing