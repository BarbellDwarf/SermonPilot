# Production Deployment Guide

## Overview
This guide covers the steps needed to run SermonPilot in production: real
credentials, environment configuration, the Docker Compose deployment, the
systemd service for bare-metal installs, and a reverse proxy.

## Production Safety Checklist

### Critical Items (Fix Before Production)

#### 1. Set Real Credentials in the Environment
All credentials come from the environment. Copy `.env.example` to `.env`
(docker compose loads it automatically) or export the variables in your
service unit, and replace every placeholder:

**Required:**
- SermonAudio API key (`SERMONAUDIO_API_KEY`) and broadcaster ID
  (`SERMONAUDIO_BROADCASTER_ID`)

**As needed:**
- LLM provider keys (`OPENAI_API_KEY`, `XAI_API_KEY`, `GROQ_API_KEY`,
  `OPENROUTER_API_KEY`) or a reachable Ollama host (`OLLAMA_HOST`)
- `APP_PASSWORD` when the UI is reachable beyond localhost

On first launch the environment values are seeded into the SQLite settings
database and persist from then on. Environment variables keep precedence over
stored settings for each running process, so rotating a key in `.env` and
restarting is enough.

#### 2. Remove Demo/Test Files and Values

#### 3. Never Commit Secrets
`.env` is gitignored. Do not paste real keys into YAML files, tickets, or
logs. The Settings export masks secrets; never store unmasked keys in
imported files.

### Medium Priority Items

#### 1. Code Quality Improvements
Large files should be refactored for maintainability:
- `ui/ui_pages/settings.py`
- `ui/ui_pages/analytics.py`
- `ui/ui_pages/library.py`

#### 2. Logging and Monitoring
Implement production logging:
- Replace debug prints with proper logging
- Set up error tracking and monitoring
- Configure log rotation and retention

#### 3. Performance Optimization
- Enable caching for expensive operations
- Configure connection pooling for databases
- Set up resource monitoring

## Deployment Architecture

### Recommended Stack (Docker Compose)

`docker-compose.yml` at the repository root runs the Streamlit UI in a
container from `ghcr.io/barbelldwarf/sermonpilot`. Key properties:

- **Image variants**: set `SERMONPILOT_TAG` to `cpu`, `rocm`, `cuda`, a
  versioned tag such as `v1.6.2-rocm`, or `latest` (latest CUDA build).
  Each image ships a matching config template under `config/templates/`
  and prints its path at startup; import it from the Settings page or point
  `SA_UPDATER_CONFIG` at it. The templates differ only in the transcription
  section.
- **Persistent data**: named volumes mount `/data` (SQLite databases,
  `DATABASE_URL` defaults to `sqlite:///data/sermon_processor.db`),
  `/models`, `/app/api_cache`, `/app/processed_sermons`,
  `/home/sermonapp/.cache`, and `/app/logs`.
- **Environment**: the compose file passes through `APP_PASSWORD`,
  `OLLAMA_HOST` (defaulting to `http://host.docker.internal:11434`),
  `DATABASE_URL`, `SERMONAUDIO_*`, `OPENAI_API_KEY`, `XAI_API_KEY`, `DEBUG`,
  and anything else in `.env` via `env_file`. `HOST_BIND` controls the
  published port's bind address (default `127.0.0.1`).
- **Startup**: the entrypoint creates and repairs volume ownership for the
  `sermonapp` user, initializes the database, and starts Streamlit on port
  8501 with a health check.

```bash
cp .env.example .env   # fill in real values
SERMONPILOT_TAG=cpu docker compose up -d
```

### Alternative Stack (bare metal)

- **Application**: Streamlit served by the Streamlit server (no WSGI layer)
- **Database**: SQLite (`sermon_processor.db`) for the UI and settings;
  ChromaDB for the analytics vector store
- **Monitoring**: system metrics collected by `ui/performance_monitor.py`

### Environment Setup

#### 1. Production Environment Variables

```bash
# Application Configuration
ENVIRONMENT=production
DEBUG=false

# API Configuration
SERMONAUDIO_API_KEY=your-production-sermonaudio-key
SERMONAUDIO_BROADCASTER_ID=your-broadcaster-id
OPENAI_API_KEY=your-production-openai-key

# Optional password protection for the UI
APP_PASSWORD=your-strong-password
HOST_BIND=0.0.0.0
```

Any setting that the env map covers (`TRANSCRIPTION_BACKEND`,
`AUDIO_ENHANCEMENT_METHOD`, `OUTPUT_DIRECTORY`, `EMBEDDING_PROVIDER`, ...)
can be set the same way; see the Configuration section of the README for the
full list. Values you do not set fall back to what is stored in the settings
database, then to built-in defaults.

#### 2. Production Dependencies
```bash
# Install from the manifest (single source of truth)
uv sync

# Or install the derived requirements files
uv pip install -r requirements/requirements.txt
uv pip install -r ui/requirements-ui.txt

# For GPU acceleration (optional)
uv pip install -r requirements/requirements-gpu.txt --index-strategy unsafe-best-match
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
User=sermonapp
WorkingDirectory=/opt/sermon-pilot
Environment=PYTHONPATH=/opt/sermon-pilot
EnvironmentFile=/opt/sermon-pilot/.env
ExecStart=/opt/sermon-pilot/.venv/bin/python -m streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0
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

## Pre-Production Testing

### 1. Run Comprehensive Test Suite
```bash
# Test all components
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

## Production Monitoring

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

## Maintenance

### Regular Tasks
- Monitor log files for errors
- Check API quota usage
- Update dependencies
- Backup the SQLite database and the vector database
- Review and rotate logs

### Incident Response
- Log aggregation and alerting
- Rollback procedures
- Performance degradation responses
- API failure handling

## Support and Troubleshooting

### Common Issues
1. **Import Errors**: See `docs/` and the project README for setup steps
2. **Configuration Issues**: Verify environment variables and the Settings
   page; `python src/secure_config.py` reports what is set
3. **API Failures**: Check API keys and quota limits
4. **Performance Issues**: Monitor resource usage via the Analytics ->
   Performance tab

### Getting Help
- Review documentation in `docs/` directory
- Run environment diagnostics with local test suite

---

**Important**: Always test configuration changes in a staging environment before production deployment.
