# Tools Directory

This directory contains utility scripts and tools for development, maintenance, and testing.

## Directory Structure

### `debug/`
Debug and diagnostic scripts:
- `debug_analytics.py` - Analytics debugging utilities
- `debug_fetch_all.py` - Batch fetching debug utilities

### `maintenance/`
Database and system maintenance scripts:
- `check_database.py` - Database health checks
- `check_jobs.py` - Job queue monitoring
- `check_schema.py` - Database schema validation

### `setup/`
Installation and setup utilities:
- `setup_database.py` - Database initialization
- `start_server.py` - Server startup utility

### `testing/`
Local testing and environment setup:
- `environment-check.py` - Environment validation
- `test-runner.py` - Local test execution
- `LOCAL_SETUP.md` - Local setup documentation

### `analysis/`
Code analysis and reporting tools:
- Various analysis scripts for code quality and testing
- Static analysis reports and utilities

### `archives/`
Archived utilities and legacy scripts

## Usage

Run scripts from the repository root directory:

```bash
# Debug utilities
python tools/debug/debug_analytics.py

# Maintenance tasks
python tools/maintenance/check_database.py

# Setup tasks
python tools/setup/setup_database.py
```