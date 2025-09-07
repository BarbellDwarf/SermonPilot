# Local Testing Requirements & Validation Guide

## 🎯 Executive Summary

This document outlines the comprehensive local testing requirements for the SermonAudio AI Audio Processor based on the completed cloud-safe analysis. The cloud environment has successfully validated the static structure, configuration schema, and code quality. Local testing is now required to validate real-world functionality, integrations, and performance.

## ✅ Cloud Analysis Completed (100% Success Rate)

### What Has Been Validated
- ✅ **UI Structure**: 32 files, 11 pages, 16,790 lines of code analyzed
- ✅ **Configuration Schema**: Valid structure with proper LLM provider support
- ✅ **Import Dependencies**: 122 Python files, 1,000 imports mapped
- ✅ **Mock Data Detection**: 143 placeholder values identified and catalogued
- ✅ **Code Quality**: Complexity analysis completed with recommendations

### Issues Identified for Local Resolution
- ⚠️ **Large UI files** (7 files >500 lines) need refactoring validation
- ⚠️ **117 unresolvable imports** need verification in full environment
- ⚠️ **22 configuration placeholders** need real credentials
- ⚠️ **Mock data patterns** need production environment testing

## 🏠 Local Environment Setup Requirements

### 1. Python Environment Setup

```bash
# Install UV package manager (if not present)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv --python 3.11
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows

# Install all dependencies
uv pip install -r requirements.txt
uv pip install -r ui/requirements-ui.txt
```

### 2. External Services Configuration

#### A. Ollama (Local LLM Server)
```bash
# Install Ollama (platform-specific)
# Linux/Mac:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# Start Ollama service
ollama serve

# Pull required models (in separate terminal)
ollama pull llama3.1:8b      # Primary model
ollama pull gemma2:2b        # Lightweight validation model

# Verify installation
ollama list
```

#### B. GPU/CUDA Setup (Optional but Recommended)
```bash
# Check CUDA availability
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}')"
python -c "import torch; print(f'CUDA Devices: {torch.cuda.device_count()}')"

# Install CUDA-compatible PyTorch if needed
# Follow PyTorch installation guide for your system
```

### 3. Configuration Setup

```bash
# Create main configuration file
cp config.example.yaml config.yaml

# Edit config.yaml with your credentials:
# - SermonAudio API key and broadcaster ID
# - OpenAI API key (if using OpenAI providers)
# - Other LLM provider keys as needed
```

### 4. Test Data Preparation (Optional)

```bash
# For audio processing tests (optional)
# Place any MP3 file at tests/sample_audio.mp3
cp your-sample-audio.mp3 tests/sample_audio.mp3
```

## 🧪 Local Testing Framework

### Phase 1: Environment Verification

```bash
# Run comprehensive environment check
python Tests/local-tests/environment-check.py
```

**Expected Output**: Verification of all dependencies, services, and configurations

### Phase 2: Core Application Testing

#### A. Streamlit UI Functionality
```bash
# Launch the web interface
streamlit run streamlit_app.py

# Manual testing checklist:
# Navigate to http://localhost:8501
```

**Manual Test Checklist**:
- [ ] **Dashboard page** loads without errors
- [ ] **New Sermon page** displays form correctly
- [ ] **Batch Update page** shows filtering options
- [ ] **Validation page** loads validation interface
- [ ] **Analytics page** displays charts and metrics
- [ ] **Jobs page** shows job queue interface
- [ ] **Library page** displays sermon search/filter
- [ ] **Settings page** loads configuration interface
- [ ] **Navigation** works between all pages
- [ ] **Form submissions** don't cause crashes (use test data)
- [ ] **Error handling** displays user-friendly messages

#### B. Configuration Management
```bash
# Test configuration loading
python -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
    print(f'Config loaded successfully')
    print(f'LLM Provider: {config.get(\"llm\", {}).get(\"primary\", {}).get(\"provider\", \"Not set\")}')
"
```

### Phase 3: Integration Testing

#### A. LLM Provider Testing
```bash
# Test LLM connections
python Tests/local-tests/test-runner.py --test-category llm
```

**Expected Validation**:
- [ ] **Primary LLM provider** connects successfully
- [ ] **Fallback provider** available and tested
- [ ] **Token counting** and usage tracking works
- [ ] **Error handling** for API failures
- [ ] **Rate limiting** compliance

#### B. SermonAudio API Integration
```bash
# Test API connectivity (requires real credentials)
python Tests/local-tests/test-runner.py --test-category api
```

**Expected Validation**:
- [ ] **API authentication** successful
- [ ] **Sermon metadata** fetching works
- [ ] **Audio file downloads** complete successfully
- [ ] **Uploads** work without errors
- [ ] **Rate limiting** respected
- [ ] **Error handling** for API failures

#### C. Audio Processing Pipeline
```bash
# Test audio enhancement (requires sample audio)
python Tests/local-tests/test-runner.py --test-category audio
```

**Expected Validation**:
- [ ] **Audio file loading** works correctly
- [ ] **AI enhancement models** load successfully (DeepFilterNet, Resemble)
- [ ] **GPU processing** works (if available)
- [ ] **CPU fallback** functions properly
- [ ] **Audio chunking** handles large files
- [ ] **Output quality** improvements measurable

#### D. RAG System Testing
```bash
# Test vector database and search
python Tests/local-tests/test-runner.py --test-category rag
```

**Expected Validation**:
- [ ] **ChromaDB** initializes correctly
- [ ] **Embeddings generation** works
- [ ] **Vector storage** and retrieval functional
- [ ] **Semantic search** returns relevant results
- [ ] **Natural language queries** processed correctly

### Phase 4: Performance Testing

#### A. Resource Monitoring
```bash
# Monitor system performance during processing
python Tests/local-tests/test-runner.py --test-category performance
```

**Monitor**:
- [ ] **CPU usage** during audio processing
- [ ] **Memory consumption** with large files
- [ ] **GPU utilization** (if available)
- [ ] **Network usage** during API calls
- [ ] **Storage usage** for processed files

#### B. Load Testing
```bash
# Test with multiple simultaneous operations
python Tests/local-tests/test-runner.py --test-category load
```

**Test Scenarios**:
- [ ] **Multiple sermon processing** simultaneously
- [ ] **Batch operations** with large datasets
- [ ] **Concurrent UI usage** simulation
- [ ] **API rate limiting** under load
- [ ] **Memory management** with sustained usage

## 🔍 Critical Test Scenarios

### Scenario 1: Complete Sermon Processing Workflow
1. **Setup**: Configure with real SermonAudio credentials
2. **Test**: Process a complete sermon from download to upload
3. **Validate**: 
   - Audio enhancement works
   - LLM generates description and hashtags
   - Upload completes successfully
   - UI reflects processing status

### Scenario 2: Error Handling and Recovery
1. **Test**: Simulate various failure conditions
   - Network interruptions
   - API rate limits
   - Invalid audio files
   - LLM provider failures
2. **Validate**: Graceful error handling and user feedback

### Scenario 3: Performance Under Load
1. **Test**: Process multiple sermons with different configurations
2. **Validate**: System stability and resource usage

### Scenario 4: Configuration Switching
1. **Test**: Switch between different LLM providers
2. **Test**: Modify audio processing settings
3. **Validate**: Changes take effect without restart

## 📊 Success Criteria

### Minimum Viable Testing
- [ ] **Streamlit UI** launches and all pages accessible
- [ ] **At least one LLM provider** functional
- [ ] **Basic configuration** loading works
- [ ] **No critical errors** during normal operation

### Complete Validation
- [ ] **All UI pages** fully functional
- [ ] **Primary and fallback LLM** providers working
- [ ] **SermonAudio API** integration complete
- [ ] **Audio processing** pipeline operational
- [ ] **RAG system** performing queries
- [ ] **Performance** acceptable under normal load
- [ ] **Error handling** graceful and informative

## 🚨 Known Issues to Test

### From Cloud Analysis
1. **Large UI Files**: Verify that complex pages (settings.py - 1,879 lines) perform well
2. **Import Resolution**: Confirm all 117 "unresolvable" imports work in full environment
3. **Mock Data**: Ensure all placeholder values replaced with real data
4. **Configuration**: Verify all 22 placeholder values properly configured

### Potential Local Issues
1. **GPU Memory**: Audio processing may require significant GPU memory
2. **Model Downloads**: First run downloads large AI models (several GB)
3. **API Limits**: SermonAudio API has rate limiting that needs testing
4. **Disk Space**: Processed audio files require storage space

## 📋 Testing Timeline

### Quick Validation (1-2 hours)
1. **Environment setup** (30 minutes)
2. **Basic UI testing** (30 minutes)
3. **Configuration validation** (30 minutes)

### Complete Testing (4-8 hours)
1. **Full integration testing** (2-3 hours)
2. **Performance testing** (1-2 hours)
3. **Error scenario testing** (1-2 hours)
4. **Documentation validation** (1 hour)

## 🛠️ Troubleshooting Guide

### Common Issues and Solutions

#### Environment Issues
- **CUDA not found**: Install CUDA toolkit or use CPU-only mode
- **Ollama connection failed**: Ensure `ollama serve` is running
- **Package installation errors**: Use UV package manager as specified

#### Configuration Issues
- **API authentication failed**: Verify API keys in config.yaml
- **Model not found**: Run `ollama pull <model-name>` for required models
- **File permissions**: Ensure write access to processing directories

#### Performance Issues
- **Out of memory**: Reduce batch sizes or use CPU processing
- **Slow processing**: Check GPU availability and model optimization
- **High disk usage**: Clean up temporary files regularly

## 📄 Reporting and Documentation

### Test Results Documentation
- **Create test logs** for each testing session
- **Document any failures** with error messages and solutions
- **Record performance metrics** for future optimization
- **Update configuration guides** based on testing experience

### Integration with Development Workflow
- **Update CI/CD** configurations based on local testing results
- **Create deployment checklists** from successful test procedures
- **Document production configuration** requirements

---

**Next Steps**: Follow this guide systematically, starting with environment setup and progressing through each testing phase. Document results and any issues encountered for future reference and continuous improvement of the testing framework.