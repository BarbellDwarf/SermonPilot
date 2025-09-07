# Security Setup Guide

## Overview

This guide helps you set up the SermonAudio Processor with proper security configurations, including environment variables, credential management, and security validation tools.

## Quick Setup

### 1. Environment Configuration

Copy the environment template and configure your credentials:

```bash
# Copy the environment template
cp .env.example .env

# Edit with your actual values
nano .env  # or your preferred editor
```

### 2. Required Environment Variables

At minimum, you need:

```bash
# SermonAudio API (Required)
SERMONAUDIO_API_KEY=your-actual-api-key-here
SERMONAUDIO_BROADCASTER_ID=your-actual-broadcaster-id

# At least one LLM provider (choose one or more)
OPENAI_API_KEY=sk-your-openai-key-here
# OR
XAI_API_KEY=xai-your-xai-key-here
# OR configure Ollama (see Ollama Setup below)
```

### 3. Configuration File

Copy and customize the configuration:

```bash
# Copy the configuration template
cp config.example.yaml config.yaml

# The config.yaml file will automatically use your environment variables
# No need to edit it manually - it references ${ENV_VAR_NAME} automatically
```

### 4. Security Validation

Validate your setup:

```bash
# Check configuration security
python src/secure_config.py

# Run security scan
python tools/security_scanner.py

# Validate overall security compliance
python tools/validate_security.py
```

## Detailed Setup Instructions

### Environment Variable Reference

See `.env.example` for the complete list of available environment variables. Key sections:

#### Required Variables
- `SERMONAUDIO_API_KEY` - Your SermonAudio API key
- `SERMONAUDIO_BROADCASTER_ID` - Your broadcaster ID

#### LLM Providers (Configure at least one)
- `OPENAI_API_KEY` - OpenAI GPT models
- `XAI_API_KEY` - xAI Grok models  
- `ANTHROPIC_API_KEY` - Anthropic Claude models
- `GROQ_API_KEY` - Groq fast inference
- `GOOGLE_API_KEY` - Google Gemini models

#### Local LLM (Alternative to API providers)
- `OLLAMA_HOST` - Ollama server URL (default: http://localhost:11434)
- `OLLAMA_PRIMARY_MODEL` - Primary model name
- `OLLAMA_FALLBACK_MODEL` - Fallback model name

### Ollama Setup (Local LLM Alternative)

If you prefer to run models locally:

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama service
ollama serve

# Pull recommended models
ollama pull llama3.1:8b      # Primary model
ollama pull gemma2:2b        # Fast validator model

# Configure environment
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_PRIMARY_MODEL=llama3.1:8b
export OLLAMA_FALLBACK_MODEL=llama2
```

### Security Best Practices

#### 1. Credential Management
- ✅ **Never** commit `.env` files to version control
- ✅ Use different API keys for development/production
- ✅ Regularly rotate API keys
- ✅ Use environment-specific configurations

#### 2. Development vs Production
```bash
# Development
DEBUG_MODE=true
DRY_RUN=true
LOG_LEVEL=DEBUG

# Production  
DEBUG_MODE=false
DRY_RUN=false
LOG_LEVEL=INFO
PRODUCTION_MODE=true
```

#### 3. Pre-commit Security Hooks
Install the pre-commit hook to prevent credential commits:

```bash
# Install the security pre-commit hook
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Test the hook
git add .
git commit -m "test commit"  # Will scan for credentials
```

### Configuration Validation

#### Automatic Validation
The system automatically validates configuration on startup:

```python
from src.secure_config import load_secure_config

# This will validate security and substitute environment variables
config = load_secure_config()
```

#### Manual Validation
Run security checks manually:

```bash
# Validate configuration security
python src/secure_config.py

# Scan for hardcoded credentials
python tools/security_scanner.py

# Run comprehensive security tests
python tools/validate_security.py
```

### Troubleshooting

#### Common Issues

**"Missing required environment variables"**
```bash
# Check which variables are missing
python src/secure_config.py

# Set missing variables in .env file
echo "SERMONAUDIO_API_KEY=your-key-here" >> .env
```

**"Hardcoded credentials detected"**
```bash
# Find the specific violations
python tools/security_scanner.py --verbose

# Replace hardcoded values with environment variables
# Example: api_key: "sk-abc123" → api_key: "${OPENAI_API_KEY}"
```

**"Configuration file not found"**
```bash
# Copy the example configuration
cp config.example.yaml config.yaml
```

#### Environment Variable Not Loading
1. Check `.env` file exists and has correct format
2. Ensure no quotes around variable names in `.env`:
   ```bash
   # Correct
   OPENAI_API_KEY=sk-abc123
   
   # Incorrect  
   "OPENAI_API_KEY"="sk-abc123"
   ```

3. Verify the variable is referenced correctly in config:
   ```yaml
   # Correct
   api_key: "${OPENAI_API_KEY}"
   
   # Incorrect
   api_key: "$OPENAI_API_KEY"
   ```

### Advanced Security Features

#### Docker Secrets (Production)
For containerized deployments:

```bash
# Docker secrets directory
export DOCKER_SECRETS_DIR=/run/secrets

# Mount secrets as files
docker run -v /host/secrets:/run/secrets sermon-processor
```

#### AWS Secrets Manager
For cloud deployments:

```bash
export AWS_REGION=us-east-1
export AWS_SECRETS_MANAGER_SECRET_NAME=sermon-processor-secrets
```

#### Security Audit Logging
Enable security audit logging:

```bash
export SECURITY_AUDIT_ENABLED=true
export SECURITY_AUDIT_LOG_PATH=logs/security_audit.log
```

## Verification Checklist

After setup, verify:

- [ ] `.env` file exists with your credentials
- [ ] `config.yaml` uses environment variables (`${VAR_NAME}` syntax)
- [ ] Security validation passes: `python tools/validate_security.py`
- [ ] Configuration loads successfully: `python src/secure_config.py`
- [ ] No hardcoded credentials detected: `python tools/security_scanner.py`
- [ ] Pre-commit hook installed and working
- [ ] LLM provider connectivity verified
- [ ] SermonAudio API connectivity verified

## Next Steps

Once security is configured:

1. **Test the system**: Run `python sermon_updater.py --list-only` to test API connectivity
2. **Configure audio processing**: Set up audio enhancement models
3. **Set up web interface**: Run `streamlit run streamlit_app.py`
4. **Process sermons**: Begin processing with proper security in place

## Support

For security-related issues:
- Review the security scanner output: `python tools/security_scanner.py`
- Check configuration validation: `python src/secure_config.py`
- Run security compliance tests: `python tools/validate_security.py`

For general setup issues, see the main README.md and documentation in the `docs/` directory.