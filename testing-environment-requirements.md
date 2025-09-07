# Testing Environment Requirements

## Overview
This document defines the testing capabilities and requirements for cloud vs local environments in the SermonAudio Processor project.

## Cloud Environment (GitHub Copilot Runners) ☁️

### Capabilities
- ✅ **Static Code Analysis**: AST parsing, syntax validation, import analysis
- ✅ **Configuration Validation**: YAML schema validation, config structure checks
- ✅ **File Structure Verification**: Directory structure, file organization validation
- ✅ **Documentation Updates**: README, guides, API documentation
- ✅ **Mock Data Identification**: Pattern scanning for hardcoded test data
- ✅ **UI Component Mapping**: Component structure analysis without execution
- ✅ **Import/Dependency Analysis**: Module resolution and dependency graphs

### Limitations
- ❌ **No External API Calls**: Cannot connect to SermonAudio API, OpenAI, etc.
- ❌ **No Local Services**: Cannot run Ollama, databases, or local servers
- ❌ **No GPU Operations**: No CUDA, audio processing AI models
- ❌ **No File I/O Operations**: Cannot process real audio files
- ❌ **No Interactive UI Testing**: Cannot launch Streamlit server

### Cloud-Safe Test Categories
1. **Static Analysis Tests**
   - Code structure validation
   - Import statement verification
   - Configuration schema checking
   - Documentation completeness

2. **Mock Data Detection**
   - Hardcoded test data identification
   - Placeholder value scanning
   - Demo data pattern recognition

3. **Configuration Validation**
   - YAML structure verification
   - Required field validation
   - Default value checking

## Local Environment (User Setup Required) 🏠

### Prerequisites
```bash
# Core requirements
Python 3.11+ with UV package manager
CUDA-capable GPU (optional, for AI audio processing)
Valid SermonAudio API credentials
ChromaDB dependencies

# Installation
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -r ui/requirements-ui.txt

# External services
ollama serve
ollama pull llama3.1:8b
```

### Full Capabilities
- ✅ **Live SermonAudio API Integration**: Real API calls, data fetching, uploads
- ✅ **LLM Provider Testing**: OpenAI, Ollama, multi-provider fallback
- ✅ **Audio Processing Pipeline**: AI enhancement, GPU/CPU processing
- ✅ **ChromaDB/RAG System**: Vector embeddings, semantic search
- ✅ **Streamlit UI Execution**: Full interactive web interface
- ✅ **Performance Monitoring**: Real-time system metrics
- ✅ **End-to-end Integration**: Complete workflow testing

### Local Test Categories
1. **API Integration Tests**
   - SermonAudio API connectivity
   - LLM provider responses
   - Rate limiting compliance
   - Error handling validation

2. **UI Functional Tests**
   - Streamlit page rendering
   - Form submission workflows
   - Navigation and routing
   - Interactive component behavior

3. **Audio Processing Tests**
   - AI model loading and execution
   - Audio enhancement pipelines
   - GPU/CPU fallback mechanisms
   - File processing workflows

4. **RAG System Tests**
   - Vector database operations
   - Semantic search functionality
   - Natural language query processing
   - Embedding generation

## Environment-Specific Testing Strategy

### Phase 1: Cloud Environment (Immediate)
Execute all tests that don't require external dependencies:
```bash
python Tests/cloud-tests/static-analysis.py
python Tests/cloud-tests/config-validation.py
python Tests/cloud-tests/import-checks.py
python Tests/cloud-tests/mock-data-scan.py
```

### Phase 2: Local Environment (User Setup)
After local environment configuration:
```bash
python Tests/local-tests/environment-check.py
streamlit run ui/streamlit_app.py
python Tests/local-tests/api-integration-tests.py
python Tests/local-tests/ui-functionality-tests.py
```

## Testing Framework Organization

### Cloud Tests (`/Tests/cloud-tests/`)
- `static-analysis.py` - Code structure and syntax validation
- `config-validation.py` - Configuration schema and structure
- `import-checks.py` - Module resolution and dependency verification
- `mock-data-scan.py` - Hardcoded data and placeholder identification
- `ui-component-analysis.py` - Static UI structure mapping

### Local Tests (`/Tests/local-tests/`)
- `environment-check.py` - Local dependency and service verification
- `api-integration-tests.py` - Live API connectivity and functionality
- `ui-functionality-tests.py` - Interactive Streamlit testing
- `audio-processing-tests.py` - AI model and pipeline testing
- `rag-system-tests.py` - Vector database and search testing

### Shared Utilities (`/Tests/utils/`)
- `test-runner.py` - Orchestrate test execution
- `environment-detector.py` - Detect cloud vs local capabilities
- `mock-data-utils.py` - Mock data identification and replacement
- `config-utils.py` - Configuration validation helpers

## Safety Guidelines

### Cloud Environment
- ⚠️ **Never attempt external API calls**: All external dependencies must be mocked
- ⚠️ **No file system writes**: Use in-memory operations for analysis
- ⚠️ **No subprocess execution**: Static analysis only
- ⚠️ **No network operations**: All network-dependent code must be bypassed

### Local Environment
- ⚠️ **Verify credentials before testing**: Check API keys and service availability
- ⚠️ **Monitor resource usage**: Audio processing can be resource-intensive
- ⚠️ **Respect rate limits**: SermonAudio API has usage restrictions
- ⚠️ **Backup configurations**: Create backups before modifying config files

## Success Criteria

### Cloud Environment Validation
- [ ] All static analysis tests pass
- [ ] Configuration structure validated
- [ ] Mock data catalog complete
- [ ] Import dependencies resolved
- [ ] Documentation updated and complete

### Local Environment Validation
- [ ] Streamlit UI launches and functions correctly
- [ ] All external integrations working (APIs, Ollama, etc.)
- [ ] Audio processing pipeline operational
- [ ] RAG system performing semantic queries
- [ ] Performance monitoring displaying real metrics
- [ ] No mock data in production code paths