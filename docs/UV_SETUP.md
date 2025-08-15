# Using UV with SermonAudio Updater

UV is a fast Python package and project manager that makes it easy to manage Python versions and dependencies.

## Quick Start with UV

1. **Install UV** (if not already installed):
   ```bash
   # Windows (PowerShell)
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Create virtual environment with specific Python version**:
   ```bash
   # Use Python 3.11 (recommended)
   uv venv --python 3.11
   
   # Or use Python 3.10
   uv venv --python 3.10
   
   # Or use Python 3.12
   uv venv --python 3.12
   ```

3. **Activate the virtual environment**:
   ```bash
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   
   # Windows (Command Prompt)
   .venv\Scripts\activate.bat
   
   # macOS/Linux
   source .venv/bin/activate
   ```

4. **Install dependencies**:
   ```bash
   # Install from requirements.txt
   uv pip install -r requirements.txt
   
   # Or install from pyproject.toml
   uv pip install -e .
   
   # Install with dev dependencies
   uv pip install -e ".[dev]"
   ```

## UV Commands Reference

### Python Version Management
```bash
# List available Python versions
uv python list

# Install a specific Python version
uv python install 3.11

# Create venv with latest Python 3.11
uv venv --python 3.11

# Create venv with exact version
uv venv --python 3.11.7
```

### Package Management
```bash
# Install packages
uv pip install package-name

# Install from requirements file
uv pip install -r requirements.txt

# Show installed packages
uv pip list

# Upgrade package
uv pip install --upgrade package-name

# Sync dependencies (remove unused)
uv pip sync requirements.txt
```

### Common Workflows

#### Fresh Setup
```bash
# Clone and setup
git clone <repo-url>
cd sa-updater
uv venv --python 3.11
.venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
```

#### Switch Python Version
```bash
# Remove old venv
rm -rf .venv  # or rmdir /s .venv on Windows

# Create new venv
uv venv --python 3.12
.venv\Scripts\activate
uv pip install -r requirements.txt
```

#### Update Dependencies
```bash
# Update all packages
uv pip install --upgrade -r requirements.txt

# Update specific package
uv pip install --upgrade sermonaudio
```

## Troubleshooting

### "Python version X.Y not found"
UV will automatically download Python versions as needed. If you get this error:
```bash
# List available versions
uv python list

# Install the version you need
uv python install 3.11
```

### Package Installation Issues
```bash
# Clear UV cache
uv cache clean

# Install with verbose output
uv pip install -v package-name
```

### Windows PowerShell Execution Policy
If you can't run the activate script:
```powershell
# Allow script execution for current session
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# Then activate
.venv\Scripts\Activate.ps1
```

## Benefits of Using UV

1. **Fast**: Much faster than pip for dependency resolution
2. **Python Version Management**: No need for pyenv or separate Python installations
3. **Reproducible**: Locks dependencies for consistent environments
4. **Cross-platform**: Works the same on Windows, macOS, and Linux
5. **Drop-in Replacement**: Compatible with pip commands

## VS Code Integration

Add to `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
    "python.terminal.activateEnvironment": true
}
```

This will automatically use the UV-created virtual environment in VS Code.
