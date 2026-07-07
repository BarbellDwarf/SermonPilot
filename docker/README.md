# Docker Usage Guide

This document explains how to use Docker with the SermonPilot.

## Quick Start

### Development Environment

1. **Start Development Stack**:
   ```bash
   ./docker-start-dev.sh
   ```
   This will start the application at http://localhost:8501

2. **Build Images Only**:
   ```bash
   ./docker-build.sh
   ```

3. **Manual Development Start**:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
   ```

### Production Environment

1. **Configure Environment**:
   Create `.env.prod` with your production settings:
   ```bash
   cp .env.prod.example .env.prod
   # Edit .env.prod with your API keys and passwords
   ```

2. **Start Production Stack**:
   ```bash
   ./docker-start-prod.sh
   ```

## Available Services

- **Main Application**: http://localhost:8501 (Streamlit UI)
- **API Endpoint**: http://localhost:8000 (FastAPI/metrics)
- **Ollama**: http://localhost:11434 (LLM inference)
- **Redis**: localhost:6379 (caching/job queue)
- **PostgreSQL**: localhost:5432 (production database)

## Docker Commands

### Basic Operations
```bash
# Build all images
docker compose build

# Start services
docker compose up -d

# View logs
docker compose logs -f sermon-processor

# Stop services
docker compose down

# Remove everything including volumes
docker compose down -v
```

### Development
```bash
# Start with code mounting
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Run tests in container
docker compose exec sermon-processor pytest tests/

# Access container shell
docker compose exec sermon-processor bash
```

### Production
```bash
# Start production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Scale application
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale sermon-processor=3

# Health check
docker compose ps
```

## Volume Management

### Data Persistence
- `sermon_data`: Application data and processed sermons
- `sermon_models`: AI model cache
- `sermon_logs`: Application logs
- `ollama_data`: Ollama model storage
- `redis_data`: Redis persistence

### Backup
```bash
# Backup sermon data
docker run --rm -v sermon-processor_sermon_data:/data -v $(pwd):/backup alpine tar czf /backup/sermon_data_backup.tar.gz /data

# Restore sermon data
docker run --rm -v sermon-processor_sermon_data:/data -v $(pwd):/backup alpine tar xzf /backup/sermon_data_backup.tar.gz
```

## Troubleshooting

### GPU Support
Ensure NVIDIA Docker runtime is installed:
```bash
# Check GPU access
docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
```

### Service Dependencies
```bash
# Check Ollama is running
curl http://localhost:11434/api/tags

# Check Redis
redis-cli ping

# Check application health
curl http://localhost:8501/healthz
```

### Common Issues

1. **Port conflicts**: Change ports in docker-compose.yml
2. **GPU not available**: Remove GPU requirements or install NVIDIA Docker
3. **Volume permissions**: Check user permissions in containers
4. **Out of memory**: Reduce model sizes or increase container limits

## Configuration

### Environment Variables
Set these in your `.env.prod` file or docker-compose environment:

- `OLLAMA_HOST`: Ollama service URL
- `DATABASE_URL`: Database connection string
- `SERMONAUDIO_API_KEY`: SermonAudio API key
- `OPENAI_API_KEY`: OpenAI API key
- `CUDA_VISIBLE_DEVICES`: GPU device selection

### Custom Configuration
Mount your config.yaml:
```yaml
volumes:
  - ./config.yaml:/app/config.yaml:ro
```