# Mock Data Removal and Security Hardening Plan

## Executive Summary

This plan addresses the critical security issue identified during testing: 704 production-unsafe files containing hardcoded credentials, test data, and mock patterns across the SermonAudio Processor codebase.

## Scope and Impact

### Current State
- **704 production-unsafe files** with hardcoded credentials
- **11,542 mock patterns** detected across codebase
- **6,957 placeholder values** requiring attention
- **Critical security risk** for production deployment

### Target State
- Zero hardcoded credentials in source code
- All test data properly isolated in test directories
- Environment-based configuration for all sensitive data
- Production-ready security posture

## Phase 1: Immediate Security Fixes (Week 1)

### 1.1 Critical Files Remediation

#### config.yaml Security Fix
**Current Issue**: Contains hardcoded API keys and credentials
```yaml
# REMOVE THESE IMMEDIATELY:
api_key: [REDACTED_API_KEY]
broadcaster_id: [REDACTED_BROADCASTER_ID]
xai.api_key: [REDACTED_XAI_API_KEY]
```

**Solution**:
```yaml
# Replace with environment variables:
api_key: ${SERMONAUDIO_API_KEY}
broadcaster_id: ${SERMONAUDIO_BROADCASTER_ID}
xai.api_key: ${XAI_API_KEY}
```

#### sermon_updater.py Hardcoded Values
**Lines to Fix**: 10, 23, 1199
- Remove hardcoded ID `12345`
- Replace temp directories with dynamic paths
- Remove placeholder broadcaster IDs

#### test_sermonaudio_api.py Test Data
**Action**: Move to proper test directory structure
- Rename test functions to avoid production confusion
- Add clear test data markers
- Isolate from production code paths

### 1.2 Environment Variable Migration

Create comprehensive `.env.example` file:
```bash
# SermonAudio API Configuration
SERMONAUDIO_API_KEY=your-api-key-here
SERMONAUDIO_BROADCASTER_ID=your-broadcaster-id

# LLM Provider API Keys
OPENAI_API_KEY=your-openai-key-here
XAI_API_KEY=your-xai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
GROQ_API_KEY=your-groq-key-here
GOOGLE_API_KEY=your-google-key-here

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434

# Database Configuration
DATABASE_URL=sqlite:///sermon_processor.db

# Audio Processing
AUDIO_PROCESSING_TEMP_DIR=/tmp/sermon_audio
AUDIO_ENHANCEMENT_METHOD=resemble_enhance

# Debug and Logging
DEBUG_MODE=false
LOG_LEVEL=INFO
```

### 1.3 Configuration Loading Security

Update config loading to use environment variables with secure defaults:

```python
import os
from pathlib import Path
from typing import Any, Dict
import yaml

def load_secure_config() -> Dict[str, Any]:
    """Load configuration with environment variable substitution."""
    config_file = Path("config.yaml")
    
    if not config_file.exists():
        raise FileNotFoundError("config.yaml not found")
    
    with open(config_file, 'r') as f:
        config_text = f.read()
    
    # Replace environment variables
    config_text = os.path.expandvars(config_text)
    config = yaml.safe_load(config_text)
    
    # Validate required environment variables
    required_vars = [
        'SERMONAUDIO_API_KEY',
        'SERMONAUDIO_BROADCASTER_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {missing_vars}")
    
    return config
```

## Phase 2: Test Data Isolation (Week 2)

### 2.1 Test Directory Restructuring

Create proper test isolation:
```
tests/
├── fixtures/
│   ├── sample_audio/
│   ├── mock_configs/
│   └── test_data/
├── unit/
├── integration/
└── e2e/
```

### 2.2 Mock Data Patterns Cleanup

**Files Requiring Immediate Attention**:

1. **examples_config.yaml** (18 placeholder values)
   - Move to `tests/fixtures/mock_configs/`
   - Add clear "EXAMPLE ONLY" headers
   - Remove from production builds

2. **README.md** (6 placeholder values)
   - Replace hardcoded examples with environment variable references
   - Update setup instructions for security

3. **Documentation Files**
   - Replace all `12345` with `${EXAMPLE_ID}`
   - Add security warnings for production setup

### 2.3 Automated Security Scanning

Create pre-commit hook to prevent credential commits:

```python
#!/usr/bin/env python3
"""Pre-commit hook to detect hardcoded credentials."""

import re
import sys
from pathlib import Path

# Patterns that indicate hardcoded credentials
CREDENTIAL_PATTERNS = [
    r'api_key:\s*["\']?[a-zA-Z0-9-]{20,}["\']?',
    r'password:\s*["\']?[^$][^{][^}]+["\']?',
    r'secret:\s*["\']?[a-zA-Z0-9]{16,}["\']?',
    r'token:\s*["\']?[a-zA-Z0-9-_]{20,}["\']?',
    r'key:\s*["\']?sk-[a-zA-Z0-9]+["\']?',  # OpenAI keys
    r'key:\s*["\']?xai-[a-zA-Z0-9]+["\']?',  # XAI keys
]

def scan_file(file_path: Path) -> list:
    """Scan file for credential patterns."""
    violations = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        for line_num, line in enumerate(content.splitlines(), 1):
            for pattern in CREDENTIAL_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    # Skip if it's an environment variable reference
                    if '${' in line or '$ENV{' in line:
                        continue
                    violations.append(f"{file_path}:{line_num} - {line.strip()}")
    
    except UnicodeDecodeError:
        # Skip binary files
        pass
    
    return violations

if __name__ == "__main__":
    violations = []
    
    # Scan staged files
    for file_path in Path(".").rglob("*"):
        if file_path.is_file() and not any(exclude in str(file_path) for exclude in ['.git', '__pycache__', '.venv']):
            violations.extend(scan_file(file_path))
    
    if violations:
        print("❌ SECURITY VIOLATION: Hardcoded credentials detected!")
        for violation in violations:
            print(f"  {violation}")
        print("\n🔧 Fix: Replace with environment variables or move to .env file")
        sys.exit(1)
    
    print("✅ No hardcoded credentials detected")
```

## Phase 3: Production Security Hardening (Week 3)

### 3.1 Secret Management Integration

Implement proper secret management:

```python
class SecretManager:
    """Secure secret management for production deployment."""
    
    def __init__(self):
        self.secrets = {}
        self._load_secrets()
    
    def _load_secrets(self):
        """Load secrets from secure sources."""
        # 1. Environment variables (highest priority)
        self.secrets.update(dict(os.environ))
        
        # 2. Docker secrets (if in container)
        secrets_dir = Path("/run/secrets")
        if secrets_dir.exists():
            for secret_file in secrets_dir.iterdir():
                if secret_file.is_file():
                    key = secret_file.name.upper()
                    with open(secret_file, 'r') as f:
                        self.secrets[key] = f.read().strip()
        
        # 3. AWS Secrets Manager (if configured)
        if os.getenv('AWS_REGION'):
            self._load_aws_secrets()
    
    def get_secret(self, key: str, default: str = None) -> str:
        """Get secret value securely."""
        value = self.secrets.get(key, default)
        if value is None:
            raise ValueError(f"Required secret '{key}' not found")
        return value
```

### 3.2 Configuration Validation

Add runtime configuration validation:

```python
def validate_production_config(config: Dict[str, Any]) -> None:
    """Validate configuration for production safety."""
    violations = []
    
    # Check for hardcoded values
    def check_hardcoded(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                check_hardcoded(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, str):
            # Check for obvious hardcoded patterns
            if any(pattern in obj.lower() for pattern in [
                'your-', 'example', 'test', 'demo', 'sample', '12345'
            ]):
                violations.append(f"Hardcoded value at {path}: {obj}")
    
    check_hardcoded(config)
    
    if violations:
        raise ValueError(f"Configuration validation failed: {violations}")
```

### 3.3 Audit and Monitoring

Implement security auditing:

```python
import logging
from datetime import datetime
from pathlib import Path

class SecurityAuditor:
    """Security event auditing."""
    
    def __init__(self):
        self.audit_log = Path("logs/security_audit.log")
        self.audit_log.parent.mkdir(exist_ok=True)
        
        # Configure secure logging
        self.logger = logging.getLogger("security_audit")
        handler = logging.FileHandler(self.audit_log)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_config_access(self, config_key: str, source: str):
        """Log configuration access."""
        self.logger.info(f"Config access: {config_key} from {source}")
    
    def log_credential_access(self, credential_type: str):
        """Log credential access."""
        self.logger.info(f"Credential access: {credential_type}")
    
    def scan_for_violations(self) -> Dict[str, Any]:
        """Scan codebase for security violations."""
        # Implementation for ongoing security scanning
        pass
```

## Phase 4: Testing and Validation (Week 4)

### 4.1 Security Test Suite

Create comprehensive security tests:

```python
import pytest
import tempfile
from pathlib import Path

class TestSecurityCompliance:
    """Test suite for security compliance."""
    
    def test_no_hardcoded_credentials(self):
        """Ensure no hardcoded credentials in source code."""
        violations = []
        
        for file_path in Path(".").rglob("*.py"):
            with open(file_path) as f:
                content = f.read()
                # Test for credential patterns
                if re.search(r'api_key\s*=\s*["\'][^$][^{]', content):
                    violations.append(str(file_path))
        
        assert not violations, f"Hardcoded credentials found in: {violations}"
    
    def test_environment_variable_usage(self):
        """Test that all configuration uses environment variables."""
        config = load_secure_config()
        
        # Verify no hardcoded values
        assert "${" in str(config) or all(
            isinstance(v, (int, bool, float)) or v.startswith("${")
            for v in self._extract_string_values(config)
        )
    
    def test_production_safety(self):
        """Test production safety measures."""
        # Test that debug mode is disabled
        config = load_secure_config()
        assert not config.get("debug", False)
        
        # Test that test endpoints are disabled
        # Additional production safety checks
```

### 4.2 Automated Compliance Checking

CI/CD pipeline integration:

```yaml
# .github/workflows/security-check.yml
name: Security Compliance Check

on: [push, pull_request]

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run credential scan
        run: |
          python tools/security_scanner.py
          
      - name: Run security tests
        run: |
          pytest tests/security/
          
      - name: Check for mock data
        run: |
          python Tests/cloud-tests/mock-data-scan.py
          if [ $? -ne 0 ]; then
            echo "❌ Mock data detected in production code"
            exit 1
          fi
```

## Implementation Timeline

### Week 1: Emergency Security Fixes
- [ ] Remove hardcoded credentials from config.yaml
- [ ] Implement environment variable loading
- [ ] Fix critical files (sermon_updater.py, config files)
- [ ] Create .env.example template

### Week 2: Test Data Isolation
- [ ] Restructure test directories
- [ ] Move mock data to proper test locations
- [ ] Clean up documentation placeholders
- [ ] Implement pre-commit security hooks

### Week 3: Production Hardening
- [ ] Implement SecretManager class
- [ ] Add configuration validation
- [ ] Set up security auditing
- [ ] Docker secrets integration

### Week 4: Testing and Deployment
- [ ] Complete security test suite
- [ ] Set up CI/CD security pipeline
- [ ] Production deployment testing
- [ ] Security documentation

## Success Metrics

- [ ] Zero hardcoded credentials in source code
- [ ] 100% environment variable usage for sensitive data
- [ ] All test data isolated in test directories
- [ ] Automated security scanning in CI/CD
- [ ] Production-ready security posture
- [ ] Security audit logging implemented

## Risk Mitigation

### High Risk
- **Credential Exposure**: Immediate removal of hardcoded credentials
- **Test Data Leakage**: Proper isolation of test data

### Medium Risk
- **Configuration Drift**: Automated validation and monitoring
- **Access Control**: Implement proper secret management

### Low Risk
- **Documentation**: Update security guidelines
- **Training**: Team security awareness

## Tools and Dependencies

### Required Tools
- `python-dotenv` for environment variable loading
- `pyyaml` for configuration parsing
- Pre-commit hooks for security scanning
- GitHub Actions for CI/CD security checks

### Optional Tools
- AWS Secrets Manager for cloud deployment
- HashiCorp Vault for enterprise secret management
- Security scanning tools (Bandit, Safety)

## Post-Implementation Monitoring

### Ongoing Security Measures
1. **Weekly Security Scans**: Automated scanning for new violations
2. **Configuration Audits**: Regular review of configuration changes
3. **Access Logging**: Monitor credential and configuration access
4. **Vulnerability Scanning**: Regular dependency security updates

### Incident Response Plan
1. **Detection**: Automated alerts for security violations
2. **Response**: Immediate credential rotation procedures
3. **Recovery**: Rapid deployment of security fixes
4. **Learning**: Post-incident security improvements

This plan ensures the SermonAudio Processor achieves production-ready security standards while maintaining development velocity and operational excellence.
