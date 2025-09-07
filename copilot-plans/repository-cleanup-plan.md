# Repository Cleanup and Organization Plan

## Executive Summary

This plan outlines a comprehensive cleanup and reorganization of the SermonAudio Processor repository to improve maintainability, reduce clutter, and establish a cleaner, more professional structure. The plan addresses file organization, removal of unnecessary artifacts, and better separation of concerns.

## Current Repository Analysis

### Files Identified for Cleanup

#### Temporary/Debug Files
- `server.log` - Server logs should not be in repo
- `sermon_processor.db` - SQLite database file should not be in repo
- `debug_analytics.py` - Debug script, should be moved to tools/
- `debug_fetch_all.py` - Debug script, should be moved to tools/
- `test-log.md` - Test logs should not be in repo
- `copilot-plan.md` - Old plan file, superseded by copilot-plans/

#### Cache/Generated Directories
- `analytics_cache/` - Should be in .gitignore
- `analytics_vector_db/` - Should be in .gitignore
- `api_cache/` - Should be in .gitignore
- `processed_sermons/` - Should be in .gitignore
- `__pycache__/` - Should be in .gitignore
- `.pytest_cache/` - Should be in .gitignore
- `.ruff_cache/` - Should be in .gitignore
- `.playwright-mcp/` - Should be in .gitignore

#### Duplicate/Redundant Files
- Multiple start scripts: `start_server.bat`, `start_server.py`, `start_server.sh`, `start_streamlit.bat`, `start_streamlit.ps1`, `server.sh`
- Multiple requirement files scattered around
- `LOCAL_TESTING_REQUIREMENTS.md` and `testing-environment-requirements.md` - duplicate content
- `examples_config.yaml` and `config.example.yaml` - should consolidate

#### Test Organization Issues
- `Tests/` and `tests/` - inconsistent naming
- Test files mixed with implementation files
- `test_sermonaudio_api.py` - should be in tests/ directory

### Current Structure Problems
1. **Mixed concerns**: Scripts, configs, and application code at root level
2. **Cache pollution**: Generated files committed to repo
3. **Duplicate functionality**: Multiple ways to start the application
4. **Inconsistent naming**: Mixed case and pluralization
5. **Documentation sprawl**: Docs in multiple locations

## Phase 1: File Removal and Cleanup (Week 1)

### 1.1 Remove Unnecessary Files

**Files to Delete:**
```bash
# Remove logs and databases
rm server.log
rm sermon_processor.db
rm test-log.md

# Remove old plan file
rm copilot-plan.md

# Remove duplicate requirement docs
rm LOCAL_TESTING_REQUIREMENTS.md  # Keep testing-environment-requirements.md
```

### 1.2 Clean Cache and Generated Files

**Update .gitignore:**
```gitignore
# Add to .gitignore
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
.pytest_cache/
.ruff_cache/
.playwright-mcp/
.coverage
htmlcov/
*.egg-info/
dist/
build/

# Application data
analytics_cache/
analytics_vector_db/
api_cache/
processed_sermons/
*.db
*.sqlite
*.sqlite3

# Logs
*.log
logs/
server.log

# Environment
.venv/
.env
.env.local
```

**Remove existing cache files:**
```bash
# Remove cache directories
rm -rf __pycache__/
rm -rf .pytest_cache/
rm -rf .ruff_cache/
rm -rf .playwright-mcp/
rm -rf analytics_cache/
rm -rf analytics_vector_db/
rm -rf api_cache/
rm -rf processed_sermons/
```

### 1.3 Consolidate Configuration Files

**Merge configuration files:**
- Keep `config.example.yaml` as the primary example
- Remove `examples_config.yaml` (duplicate)
- Update `config.example.yaml` to include all necessary examples

## Phase 2: Repository Reorganization (Week 2)

### 2.1 Create New Directory Structure

**Proposed New Structure:**
```
sermon-ai-audio-processor/
├── .github/                    # GitHub Actions, templates
├── docs/                       # All documentation
├── src/                        # Core application code
│   ├── audio/                  # Audio processing modules
│   ├── llm/                    # LLM management
│   ├── sermonaudio/            # SermonAudio API integration
│   ├── validation/             # Validation and QA
│   └── utils/                  # Utility functions
├── ui/                         # Web interface code
│   ├── components/             # Reusable UI components
│   ├── pages/                  # Streamlit pages
│   └── utils/                  # UI utilities
├── tools/                      # Development and utility scripts
│   ├── debug/                  # Debug scripts
│   ├── setup/                  # Setup and installation scripts
│   └── maintenance/            # Maintenance scripts
├── tests/                      # All test files (consolidate Tests/)
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   ├── ui/                     # UI tests
│   └── fixtures/               # Test fixtures
├── requirements/               # All requirement files
│   ├── base/                   # Core requirements
│   ├── optional/               # Optional dependencies
│   └── dev/                    # Development requirements
├── scripts/                    # Startup and deployment scripts
│   ├── linux/                  # Linux-specific scripts
│   ├── windows/                # Windows-specific scripts
│   └── docker/                 # Docker-related scripts
├── config/                     # Configuration templates
├── docker/                     # Docker files and configs
└── .gitignore
```

### 2.2 Move Files to New Locations

**File Movement Plan:**

```bash
# Move debug scripts to tools/debug/
mv debug_analytics.py tools/debug/
mv debug_fetch_all.py tools/debug/

# Move test file to tests/
mv test_sermonaudio_api.py tests/unit/

# Consolidate Tests/ into tests/
mv Tests/* tests/
rmdir Tests/

# Move startup scripts to scripts/
mkdir -p scripts/linux scripts/windows
mv start_server.sh scripts/linux/
mv server.sh scripts/linux/
mv start_server.bat scripts/windows/
mv start_streamlit.bat scripts/windows/
mv start_streamlit.ps1 scripts/windows/

# Move start_server.py to tools/setup/
mv start_server.py tools/setup/

# Move check scripts to tools/maintenance/
mv check_database.py tools/maintenance/
mv check_jobs.py tools/maintenance/
mv check_schema.py tools/maintenance/
mv setup_database.py tools/setup/

# Move config examples to config/
mv config.example.yaml config/
mv examples_config.yaml config/examples.yaml  # Rename and move

# Move UI requirements to requirements/ui/
mv ui/requirements-ui.txt requirements/ui/

# Move documentation
mv README.md docs/
mv docs/* docs/  # Consolidate all docs
```

### 2.3 Update Requirements Organization

**Reorganize requirements directory:**
```bash
# Create subdirectories
mkdir -p requirements/base requirements/optional requirements/dev requirements/ui

# Move files
mv requirements.txt requirements/base/core.txt
mv requirements-cpu.txt requirements/base/cpu.txt
mv requirements-linux.txt requirements/base/linux.txt
mv requirements-dev.txt requirements/dev/core.txt
mv requirements-gpu.txt requirements/optional/gpu.txt
mv requirements-gpu-full.txt requirements/optional/gpu-full.txt
mv requirements-gpu-minimal.txt requirements/optional/gpu-minimal.txt
mv requirements-models-all.txt requirements/optional/models-all.txt
mv requirements-models-deepfilternet.txt requirements/optional/models-deepfilternet.txt
mv requirements-models-resemble.txt requirements/optional/models-resemble.txt

# Move platform-specific
mv linux/* requirements/linux/
mv windows/* requirements/windows/
rmdir linux windows
```

## Phase 3: Code Organization Improvements (Week 3)

### 3.1 Break Down Large Files

**Main application file breakdown:**
- `sermon_updater.py` (3510 lines) → Break into modules:
  - `src/sermonaudio/cli.py` - Command line interface
  - `src/sermonaudio/processor.py` - Core processing logic
  - `src/sermonaudio/batch_processor.py` - Batch processing
  - `src/sermonaudio/validation.py` - Validation logic

**UI file breakdown:**
- `streamlit_app.py` (357 lines) → Break into:
  - `ui/app.py` - Main app entry point
  - `ui/pages/dashboard.py` - Dashboard page
  - `ui/pages/processing.py` - Processing pages
  - `ui/components/navigation.py` - Navigation components

### 3.2 Create Module Structure

**New src/ structure:**
```python
src/
├── __init__.py
├── audio/
│   ├── __init__.py
│   ├── processor.py
│   ├── enhancer.py
│   └── utils.py
├── sermonaudio/
│   ├── __init__.py
│   ├── api.py
│   ├── models.py
│   └── utils.py
├── llm/
│   ├── __init__.py
│   ├── manager.py
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── ollama.py
│   │   ├── openai.py
│   │   └── xai.py
│   └── utils.py
├── validation/
│   ├── __init__.py
│   ├── description_validator.py
│   ├── qa_normalizer.py
│   └── utils.py
└── utils/
    ├── __init__.py
    ├── config.py
    ├── logging.py
    └── helpers.py
```

### 3.3 Update Import Statements

**Update all import statements** to reflect new module structure:
```python
# Before
from audio_processing import AudioProcessor
from llm_manager import LLMManager

# After
from src.audio.processor import AudioProcessor
from src.llm.manager import LLMManager
```

## Phase 4: Documentation Consolidation (Week 4)

### 4.1 Consolidate Documentation

**Move all documentation to docs/:**
```bash
# Move existing docs
mv *.md docs/ 2>/dev/null || true
mv docs/*.md docs/ 2>/dev/null || true

# Create documentation structure
mkdir -p docs/{user,developer,deployment,api}

# Organize by audience
mv docs/README.md docs/user/
mv docs/LINUX_INSTALLATION.md docs/deployment/
mv docs/AI_MODELS_INSTALLATION.md docs/deployment/
```

### 4.2 Create New Root README

**Create clean root README.md:**
```markdown
# SermonAudio Processor

[Brief description]

## Quick Start
[Installation and basic usage]

## Documentation
- [User Guide](docs/user/)
- [Developer Guide](docs/developer/)
- [Deployment Guide](docs/deployment/)
- [API Reference](docs/api/)

## Project Structure
[Overview of new directory structure]
```

## Phase 5: Update Build and CI/CD (Week 5)

### 5.1 Update pyproject.toml

**Update build configuration:**
```toml
[tool.poetry]
name = "sermon-audio-processor"
version = "1.0.0"
description = "AI-powered sermon processing and enhancement"
authors = ["Your Name <email@example.com>"]

[tool.poetry.dependencies]
python = "^3.11"
# Core dependencies...

[tool.poetry.group.dev.dependencies]
# Dev dependencies...

[tool.poetry.group.gpu.dependencies]
# GPU dependencies...

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

### 5.2 Update GitHub Actions

**Update CI/CD workflows:**
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements/base/core.txt
          pip install -r requirements/dev/core.txt
      - name: Run tests
        run: python -m pytest tests/
```

### 5.3 Update Docker Configuration

**Update Dockerfile for new structure:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements/base/core.txt requirements/base/
RUN pip install -r requirements/base/core.txt

# Copy source code
COPY src/ ./src/
COPY ui/ ./ui/
COPY tools/ ./tools/

# Set Python path
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.sermonaudio.cli"]
```

## Implementation Timeline

### Week 1: Cleanup
- [ ] Remove unnecessary files
- [ ] Update .gitignore
- [ ] Clean cache directories
- [ ] Consolidate configuration files

### Week 2: Reorganization
- [ ] Create new directory structure
- [ ] Move files to appropriate locations
- [ ] Reorganize requirements directory
- [ ] Update all import statements

### Week 3: Code Structure
- [ ] Break down large files into modules
- [ ] Create proper package structure
- [ ] Update import statements
- [ ] Test module imports

### Week 4: Documentation
- [ ] Consolidate all documentation
- [ ] Create new root README
- [ ] Update documentation links
- [ ] Create documentation index

### Week 5: Build and CI/CD
- [ ] Update pyproject.toml
- [ ] Update GitHub Actions workflows
- [ ] Update Docker configuration
- [ ] Test CI/CD pipeline

## Success Criteria

### Repository Health
- [ ] Zero unnecessary files in root directory
- [ ] Clean .gitignore with no committed cache files
- [ ] Consistent naming conventions
- [ ] Logical directory structure

### Code Quality
- [ ] Modular code structure with clear separation of concerns
- [ ] Updated import statements working correctly
- [ ] All tests passing with new structure
- [ ] Documentation accessible and up-to-date

### Developer Experience
- [ ] Clear project structure for new contributors
- [ ] Consistent development workflow
- [ ] Working CI/CD pipeline
- [ ] Comprehensive documentation

## Risk Mitigation

### Backup Strategy
- Create full repository backup before major changes
- Test all file movements in development branch
- Validate all imports after reorganization

### Testing Strategy
- Run full test suite after each phase
- Test all startup scripts in new locations
- Validate documentation links
- Test CI/CD pipeline

### Rollback Plan
- Keep development branch for iterative changes
- Document all file movements for easy reversal
- Test critical functionality after each change

This cleanup plan will transform the repository from a cluttered development workspace into a clean, professional, and maintainable codebase that follows Python best practices and modern project organization standards.
