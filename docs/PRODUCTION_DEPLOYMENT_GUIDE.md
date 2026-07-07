# Production Deployment Guide

## Overview
This guide addresses production readiness based on comprehensive testing framework analysis.

**Generated**: 2025-09-07 01:41:34

## ⚠️ Production Safety Checklist

### 🔥 Critical Items (Must Fix Before Production)

#### 1. Replace Configuration Placeholders
All placeholder values in configuration files must be replaced with real credentials:

**Files to Update:**
- `config.yaml` - Replace all `your-*-key` placeholders with real API keys
- Remove or secure any `demo-*` or `test-*` values

**Required Credentials:**
- SermonAudio API key and broadcaster ID
- LLM provider API keys (OpenAI, Anthropic, xAI, etc.)
- Database credentials (if applicable)

#### 2. Remove Demo/Test Files
Files in `examples/` directory contain demo code and should not be deployed to production:
- `examples/demo_metadata_api.py`
- `examples/demo_enhanced_providers.py`

**Action**: Exclude `examples/` directory from production deployment.

#### 3. Secure Environment Variables
Replace hardcoded credentials with environment variables:

```bash
# .env file (DO NOT commit to git)
OPENAI_API_KEY=your-real-openai-key
SERMONAUDIO_API_KEY=your-real-sermonaudio-key
SERMONAUDIO_BROADCASTER_ID=your-real-broadcaster-id
```

Update `config.yaml` to use environment variables:
```yaml
sermonaudio:
  api_key: "${SERMONAUDIO_API_KEY}"
  broadcaster_id: "${SERMONAUDIO_BROADCASTER_ID}"
```

### ⚠️ Medium Priority Items

#### 1. Code Quality Improvements
Large files should be refactored for maintainability:
- `ui/ui_pages/settings.py` (1,879 lines) - Break into smaller components
- `ui/ui_pages/analytics.py` (1,360 lines) - Extract chart components
- `ui/ui_pages/library.py` (817 lines) - Separate data and UI logic

#### 2. Logging and Monitoring
Implement production logging:
- Replace debug prints with proper logging
- Set up error tracking and monitoring
- Configure log rotation and retention

#### 3. Performance Optimization
- Enable caching for expensive operations
- Configure connection pooling for databases
- Set up resource monitoring

## 🏗️ Deployment Architecture

### Recommended Stack
- **Application**: Streamlit with production WSGI server
- **Database**: ChromaDB for vector storage
- **Caching**: Redis for session and computation caching
- **Monitoring**: Application and system metrics collection

### Environment Setup

#### 1. Production Environment Variables
```bash
# Application Configuration
APP_ENV=production
DEBUG=false
LOG_LEVEL=info

# API Configuration  
OPENAI_API_KEY=your-production-openai-key
SERMONAUDIO_API_KEY=your-production-sermonaudio-key
SERMONAUDIO_BROADCASTER_ID=your-broadcaster-id

# Database Configuration
CHROMADB_PATH=/var/lib/sermonaudio/vector_db
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

# Security
SESSION_SECRET_KEY=your-random-secret-key
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
```

#### 2. Production Dependencies
```bash
# Install production dependencies
pip install -r requirements.txt
pip install -r ui/requirements-ui.txt

# For GPU acceleration (optional)
pip install -r requirements/requirements-gpu.txt
```

### 3. System Configuration

#### Service Configuration
Create systemd service for production deployment:

```ini
[Unit]
Description=SermonPilot
After=network.target

[Service]
Type=simple
User=sermonaudio
WorkingDirectory=/opt/sermonaudio-processor
Environment=PYTHONPATH=/opt/sermonaudio-processor
ExecStart=/opt/sermonaudio-processor/.venv/bin/python -m streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Reverse Proxy Configuration (Nginx)
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for Streamlit
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## 🧪 Pre-Production Testing

### 1. Run Comprehensive Test Suite
```bash
# Test all components
python Tests/master_plan_runner.py --local

# Verify environment setup
python Tests/local-tests/environment-check.py

# Test configuration
python Tests/cloud-tests/config-validation.py
```

### 2. Performance Testing
```bash
# Test with real audio files
# Test API integrations with production credentials
# Monitor resource usage under load
```

### 3. Security Testing
- Verify no credentials in logs
- Test input validation
- Verify access controls

## 📊 Production Monitoring

### Application Metrics
- Request/response times
- Error rates and types  
- Resource usage (CPU, memory, GPU)
- API quota usage

### Business Metrics
- Sermons processed per day
- Processing success rates
- User engagement metrics
- Cost per processing job

## 🔄 Maintenance

### Regular Tasks
- Monitor log files for errors
- Check API quota usage
- Update dependencies
- Backup vector database
- Review and rotate logs

### Incident Response
- Log aggregation and alerting
- Rollback procedures
- Performance degradation responses
- API failure handling

## 📞 Support and Troubleshooting

### Common Issues
1. **Import Errors**: See `docs/IMPORT_RESOLUTION_GUIDE.md`
2. **Configuration Issues**: Verify environment variables and config.yaml
3. **API Failures**: Check API keys and quota limits
4. **Performance Issues**: Monitor resource usage and logs

### Getting Help
- Check the comprehensive test results in `Tests/archives/`
- Review documentation in `docs/` directory
- Run environment diagnostics with local test suite

---

**Important**: Always test configuration changes in a staging environment before production deployment.
