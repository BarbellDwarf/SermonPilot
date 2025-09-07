# GitHub Copilot Agent Prompt: Comprehensive UI Testing & Validation

## Mission Statement
Conduct a complete UI validation of the SermonAudio Processor Streamlit web application, ensuring production-ready state with full functionality, proper documentation, organized codebase, and elimination of all mock data.

## Testing Environment Classification

### 🌐 Cloud-Runnable Tests (GitHub Copilot Runners)
- Static code analysis
- Configuration validation
- File structure verification
- Documentation updates
- Mock data identification
- UI component mapping
- Import/dependency analysis

### 🏠 Local-Only Tests (Requires Local Environment)
- Live SermonAudio API connections
- Ollama LLM integration
- Audio processing with AI models
- ChromaDB/RAG system functionality
- Streamlit server execution
- GPU/CUDA operations
- File upload/download workflows

## Phase 1: Cloud Environment Setup & Discovery
1. **Create workspace structure**:
   - Create `/copilot-plans/` folder for all plan files
   - Create `/Tests/` folder with subfolders: `unit-tests/`, `integration-tests/`, `ui-tests/`, `local-tests/`, `cloud-tests/`, `archives/`
   - Initialize `test-log.md` in project root to track all activities
   - Create `testing-environment-requirements.md` documenting cloud vs local test requirements

2. **Application discovery (CLOUD)**:
   - Analyze the main Streamlit app structure in `/ui/streamlit_app.py`
   - Map all UI pages in `/ui/ui_pages/` directory
   - Identify navigation components in `/ui/shared_navigation.py`
   - Document current page structure and routing logic
   - Verify configuration structure in `config.yaml`
   - Analyze all Python imports and dependencies

## Phase 2: Cloud-Safe UI Analysis
3. **Static UI component analysis (CLOUD)**:
   - **Dashboard** (`/ui/ui_pages/dashboard.py`): Analyze component structure, identify data requirements
   - **New Sermon** (`/ui/ui_pages/new_sermon.py`): Review form validation logic, file handling patterns
   - **Batch Update** (`/ui/ui_pages/batch_update.py`): Examine batch operation workflows
   - **Validation** (`/ui/ui_pages/validation.py`): Check validation logic patterns
   - **Analytics** (`/ui/ui_pages/analytics.py`): Review chart configuration and data visualization setup
   - **Jobs** (`/ui/ui_pages/jobs.py`): Analyze job queue management code
   - **Library** (`/ui/ui_pages/library.py`): Examine search and filter implementations
   - **Settings** (`/ui/ui_pages/settings.py`): Review configuration management code

4. **Configuration & dependency validation (CLOUD)**:
   - Verify `config.yaml` structure matches expected schema
   - Check all Python imports resolve correctly
   - Validate environment variable usage
   - Analyze LLM provider configuration patterns
   - Review audio processing method configurations
   - Check SermonAudio API credential placeholders

## Phase 3: Local Environment Testing Strategy
5. **Create local testing framework**:
   - Generate `/Tests/local-tests/test-runner.py` for orchestrating local tests
   - Create `/Tests/local-tests/environment-check.py` to verify local dependencies
   - Document required local setup in `/Tests/local-tests/LOCAL_SETUP.md`:
     ```markdown
     # Local Testing Requirements
     
     ## Prerequisites
     - Python 3.11+ with UV package manager
     - CUDA-capable GPU (optional, for AI audio processing)
     - Ollama server running locally
     - Valid SermonAudio API credentials
     - ChromaDB dependencies
     
     ## Setup Commands
     ```bash
     uv venv --python 3.11
     source .venv/bin/activate
     uv pip install -r requirements.txt
     uv pip install -r ui/requirements-ui.txt
     
     # Start Ollama
     ollama serve
     ollama pull llama3.1:8b
     
     # Configure credentials
     cp config.yaml.example config.yaml
     # Edit config.yaml with real credentials
     ```
     
     ## Test Execution
     ```bash
     # Run local environment checks
     python Tests/local-tests/environment-check.py
     
     # Start Streamlit for manual testing
     streamlit run ui/streamlit_app.py
     
     # Run integration tests
     python Tests/local-tests/test-runner.py
     ```
     ```

6. **Local functionality tests**:
   - **SermonAudio API Integration**:
     ```python
     # Test real API connection
     - Fetch sermon metadata
     - Download audio files
     - Upload processed results
     - Verify rate limiting compliance
     ```
   
   - **LLM System Tests**:
     ```python
     # Test multi-provider LLM setup
     - OpenAI-compatible API calls
     - Ollama local inference
     - Fallback mechanism validation
     - Token usage tracking
     ```
   
   - **Audio Processing Pipeline**:
     ```python
     # Test AI enhancement workflow
     - DeepFilterNet processing
     - Resemble Enhance integration
     - GPU/CPU fallback behavior
     - Audio chunking strategies
     ```
   
   - **RAG System Validation**:
     ```python
     # Test ChromaDB integration
     - Vector embedding generation
     - Semantic search functionality
     - Natural language queries
     - Database persistence
     ```

## Phase 4: Issue Documentation & Environment-Specific Planning
7. **Create environment-aware issue plans (CLOUD)**:
   - For each identified issue, create `/copilot-plans/issue-[number].md` with:
     ```markdown
     # Issue #[number]: [Brief Description]
     
     ## Priority: [High/Medium/Low]
     ## Testing Environment: [Cloud/Local/Both]
     ## Affected Component: [Specific UI element/page]
     ## Description: [Detailed issue description]
     
     ## Cloud-Testable Elements:
     - [ ] Code structure analysis
     - [ ] Configuration validation
     - [ ] Import/dependency checks
     
     ## Local-Only Elements:
     - [ ] Live API integration
     - [ ] Real-time processing
     - [ ] Hardware-dependent features
     
     ## Steps to Reproduce:
     ### Cloud Environment:
     1. [Cloud-safe reproduction steps]
     
     ### Local Environment:
     1. [Local environment setup]
     2. [Local reproduction steps]
     
     ## Root Cause Analysis: [Technical analysis]
     ## Proposed Fix: [Environment-specific solutions]
     ## Testing Requirements: 
     - **Cloud**: [How to verify without external dependencies]
     - **Local**: [Full integration testing approach]
     ## Dependencies: [Related issues or prerequisites]
     ```

8. **Create environment-specific master plan (CLOUD)**:
   - Generate `/copilot-plans/master-plan.md` with:
     - Cloud-executable fixes (immediate)
     - Local-dependent validations (requires setup)
     - Priority matrix based on testing environment
     - Resource requirements for each environment

## Phase 5: Mock Data Elimination Strategy
9. **Identify mock data patterns (CLOUD)**:
   - Scan all files for hardcoded test data, placeholder values
   - Check `/ui/analytics_chat.py` for mock analytics responses
   - Review `/ui/sermonaudio_analytics.py` for placeholder data
   - Identify configuration placeholders vs real credentials
   - Map data flow dependencies

10. **Create mock data replacement plan (CLOUD)**:
    - Document each mock data instance with replacement strategy
    - Distinguish between:
      - **Development placeholders** (safe to replace)
      - **Demo data** (needs graceful degradation)
      - **Test fixtures** (move to test directories)
    - Create migration scripts for safe data replacement

## Phase 6: Environment-Aware Testing Execution
11. **Execute cloud-safe tests immediately**:
    ```bash
    # These run in GitHub Copilot cloud environment
    python Tests/cloud-tests/static-analysis.py
    python Tests/cloud-tests/config-validation.py
    python Tests/cloud-tests/import-checks.py
    python Tests/cloud-tests/mock-data-scan.py
    ```

12. **Generate local test suite (CLOUD)**:
    ```python
    # Create comprehensive local testing scripts
    # Tests/local-tests/streamlit-ui-tests.py
    # Tests/local-tests/api-integration-tests.py
    # Tests/local-tests/llm-provider-tests.py
    # Tests/local-tests/audio-processing-tests.py
    # Tests/local-tests/rag-system-tests.py
    ```

## Phase 7: Documentation & Cleanup
13. **Update documentation (CLOUD)**:
    - Refresh `/ui/README.md` with current testing procedures
    - Update `/README.md` with environment-specific setup
    - Create `/docs/TESTING_GUIDE.md` with cloud vs local procedures
    - Document all configuration examples with placeholder vs real value guidance

14. **Create Copilot-specific guides (CLOUD)**:
    - `copilot-instructions.md`: Best practices for cloud-safe development
    - `local-testing-guide.md`: Complete local environment setup
    - `api-integration-guide.md`: Safe credential management
    - `ui-improvements.md`: Prioritized enhancements by testing environment

## Phase 8: Environment-Specific Validation
15. **Cloud environment validation (IMMEDIATE)**:
    - All code compiles without external dependencies
    - Configuration schemas are valid
    - Import statements resolve correctly
    - Mock data is properly identified and documented
    - Test structure is properly organized

16. **Local environment validation (USER SETUP REQUIRED)**:
    - Streamlit application launches successfully
    - All pages render without errors
    - SermonAudio API integration works with real credentials
    - LLM providers respond correctly (OpenAI + Ollama)
    - Audio processing pipeline functions with sample files
    - RAG system performs semantic search
    - Performance monitoring displays real metrics

## Success Criteria

### Cloud Environment (Immediate)
- [ ] All static analysis passes
- [ ] Configuration structure validated
- [ ] Mock data catalog complete
- [ ] Test framework scaffolded
- [ ] Documentation updated
- [ ] File organization complete

### Local Environment (Requires Setup)
- [ ] Streamlit UI fully functional
- [ ] All integrations working with real APIs
- [ ] Audio processing pipeline operational
- [ ] RAG system performing queries
- [ ] Performance monitoring active
- [ ] No mock data in production paths

## Testing Commands Reference

### Cloud-Safe Commands (Run Anywhere)
```bash
# Static analysis and planning
python Tests/cloud-tests/analyze-structure.py
python Tests/cloud-tests/validate-config.py
python Tests/cloud-tests/scan-imports.py
python Tests/cloud-tests/identify-mocks.py
```

### Local Environment Commands (Requires Full Setup)
```bash
# Environment verification
python Tests/local-tests/environment-check.py

# UI testing
streamlit run ui/streamlit_app.py
python Tests/local-tests/ui-integration-tests.py

# API testing
python Tests/local-tests/sermonaudio-api-tests.py
python Tests/local-tests/llm-provider-tests.py

# Audio processing
python Tests/local-tests/audio-enhancement-tests.py

# RAG system
python Tests/local-tests/chromadb-rag-tests.py
```

## Safety Guidelines
- **Cloud Environment**: Never attempt to execute code requiring external APIs or local services
- **Local Environment**: Always verify credentials are configured before running integration tests
- **Data Safety**: Create backups before modifying any configuration files
- **Resource Management**: Monitor GPU/CPU usage during audio processing tests
- **API Limits**: Respect SermonAudio API rate limits during testing

## Deliverables Timeline

### Immediate (Cloud Environment)
- **Day 1**: Complete static analysis and issue identification
- **Day 2**: Generate comprehensive local testing framework
- **Day 3**: Document all mock data and create replacement strategies
- **Day 4**: Finalize documentation and testing guides

### Post Local Setup (User Environment)
- **Week 1**: Execute full integration testing suite
- **Week 2**: Validate all real-world integrations
- **Week 3**: Performance optimization and final validation

Execute this plan systematically, documenting progress in `test-log.md` and creating detailed environment-specific issue reports. Focus on maximizing what can be accomplished in the cloud environment while preparing comprehensive testing for local validation.