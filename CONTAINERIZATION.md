# SermonAudio Processor - Containerization Implementation

This document provides a comprehensive guide to the Docker containerization implementation for the SermonAudio Processor.

## 🎯 Implementation Overview

The containerization follows the plan outlined in `copilot-plans/containerization-plan.md` and implements:

- **Multi-stage Docker builds** with CUDA support
- **Service orchestration** with Docker Compose
- **Kubernetes deployment** manifests and Helm charts
- **Production-ready configurations** with monitoring and backup
- **Development workflows** with hot-reload and debugging

## 🚀 Quick Start

### Prerequisites
- Docker 20.10+ with Docker Compose v2
- NVIDIA Docker runtime (optional, for GPU acceleration)
- 8GB+ RAM, 50GB+ disk space

### Development Environment
```bash
# One-command setup
./setup-docker.sh

# Start development environment
./docker-start-dev.sh
```

### Production Environment
```bash
# Configure environment
cp .env.prod.example .env.prod
# Edit .env.prod with your API keys

# Start production environment
./docker-start-prod.sh
```

## 📁 File Structure

```
.
├── Dockerfile                    # Multi-stage production build
├── Dockerfile.dev                # Development with debugging tools
├── Dockerfile.prod               # Production optimized build
├── docker-compose.yml            # Base service definitions
├── docker-compose.dev.yml        # Development overrides
├── docker-compose.prod.yml       # Production configuration
├── .dockerignore                 # Docker build exclusions
├── setup-docker.sh               # Environment setup script
├── docker-start-dev.sh           # Development startup
├── docker-start-prod.sh          # Production startup
├── docker-build.sh               # Build all images
├── test_docker_setup.py          # Validation tests
├── docker/
│   ├── README.md                 # Detailed Docker documentation
│   ├── start_production.sh       # Production container startup
│   ├── wait_for_services.py      # Service dependency checks
│   ├── nginx/nginx.conf          # Reverse proxy configuration
│   ├── postgres/init.sql         # Database initialization
│   ├── prometheus/prometheus.yml # Monitoring configuration
│   └── backup/
│       ├── backup_script.sh      # Automated backup
│       └── restore_script.sh     # Disaster recovery
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   └── service.yaml
└── helm/sermon-processor/        # Helm chart
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
```

## 🐳 Docker Images

### Base Image (Dockerfile)
- **Base**: NVIDIA CUDA 12.1 + Ubuntu 22.04
- **Python**: 3.11 with UV package manager
- **Dependencies**: Audio processing, AI models, web framework
- **Size**: ~8GB (includes AI models)

### Development Image (Dockerfile.dev)
- Extends base with development tools
- Jupyter Lab, debugging utilities
- Hot-reload for code changes
- Volume mounts for source code

### Production Image (Dockerfile.prod)
- Optimized build with removed dev files
- Security hardening
- Resource limits
- Health checks

## 🔧 Service Architecture

### Core Services
- **sermon-processor**: Main Streamlit application (port 8501)
- **ollama**: Local LLM inference (port 11434)
- **redis**: Job queue and caching (port 6379)

### Production Services
- **postgres**: Production database (port 5432)
- **nginx**: Reverse proxy and load balancer (ports 80/443)

### Monitoring Services (Optional)
- **prometheus**: Metrics collection (port 9090)
- **grafana**: Metrics visualization (port 3000)

## 🔀 Deployment Options

### 1. Development (Local)
```bash
./docker-start-dev.sh
# Access: http://localhost:8501
```

### 2. Production (Docker Compose)
```bash
./docker-start-prod.sh
# Access: http://localhost
```

### 3. Kubernetes
```bash
kubectl apply -f k8s/
# Or use Helm:
helm install sermon-processor helm/sermon-processor/
```

## 📊 Resource Requirements

### Development
- **CPU**: 2+ cores
- **RAM**: 4GB minimum, 8GB recommended
- **GPU**: Optional (NVIDIA with 4GB+ VRAM)
- **Storage**: 20GB

### Production
- **CPU**: 4+ cores per replica
- **RAM**: 8GB minimum, 16GB recommended
- **GPU**: Recommended (NVIDIA with 8GB+ VRAM)
- **Storage**: 100GB+ for sermon data

## 🔐 Security Features

### Container Security
- Non-root user (UID 1000)
- Read-only root filesystem where possible
- Dropped capabilities
- Security context constraints

### Network Security
- Isolated container networks
- TLS termination at nginx
- Internal service communication only

### Secrets Management
- Environment variables for sensitive data
- Kubernetes secrets integration
- Encrypted volume storage

## 📈 Monitoring & Observability

### Health Checks
- Application: HTTP endpoint on port 8501
- Services: Custom health check scripts
- Kubernetes: Liveness and readiness probes

### Metrics
- Prometheus integration with custom metrics
- GPU utilization monitoring
- Audio processing performance
- API response times

### Logging
- Structured JSON logging
- Centralized log aggregation
- Debug and audit trails

## 💾 Backup & Recovery

### Automated Backups
```bash
# Run backup
docker/backup/backup_script.sh

# Restore from backup
docker/backup/restore_script.sh 20240907_143000
```

### Data Persistence
- **sermon_data**: Processed audio and metadata
- **ollama_data**: LLM models cache
- **postgres_data**: Database storage
- **redis_data**: Cache persistence

## 🚨 Troubleshooting

### Common Issues

1. **GPU not available**
   ```bash
   # Check GPU support
   docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
   ```

2. **Port conflicts**
   ```bash
   # Check port usage
   netstat -tlnp | grep :8501
   ```

3. **Service startup failures**
   ```bash
   # Check logs
   docker compose logs -f sermon-processor
   ```

4. **Memory issues**
   ```bash
   # Monitor resource usage
   docker stats
   ```

### Debug Commands
```bash
# Enter container shell
docker compose exec sermon-processor bash

# View container logs
docker compose logs -f

# Check service health
docker compose ps

# Rebuild with no cache
docker compose build --no-cache
```

## 🔄 Development Workflow

### Code Changes
1. Edit code locally
2. Changes automatically reflected in dev container
3. Streamlit auto-reloads on file changes
4. Test changes in browser

### Testing
```bash
# Run containerization tests
python test_docker_setup.py

# Run application tests in container
docker compose exec sermon-processor pytest tests/
```

### Building for Production
```bash
# Build all images
./docker-build.sh

# Tag for registry
docker tag sermon-processor:latest your-registry/sermon-processor:v1.0.0

# Push to registry
docker push your-registry/sermon-processor:v1.0.0
```

## 📚 Additional Resources

- [Docker Documentation](./docker/README.md) - Detailed Docker usage
- [Kubernetes Guide](./k8s/README.md) - K8s deployment guide
- [Helm Chart Documentation](./helm/sermon-processor/README.md) - Helm usage
- [Monitoring Guide](./docs/MONITORING.md) - Observability setup
- [Security Guide](./docs/SECURITY.md) - Security best practices

## 🤝 Contributing

When modifying the containerization:

1. Update relevant Dockerfiles and compose files
2. Run `python test_docker_setup.py` to validate
3. Test both development and production workflows
4. Update documentation as needed
5. Follow security best practices

## 📞 Support

For containerization issues:
1. Check logs: `docker compose logs -f`
2. Validate setup: `python test_docker_setup.py`
3. Review troubleshooting section above
4. Open issue with full error logs and system info