# Containerization Plan for SermonAudio Processor

## Executive Summary

This plan outlines the complete containerization strategy for the SermonAudio Processor application, including Docker configuration, orchestration, production deployment, and operational considerations.

## Current State Analysis

### Application Architecture
- **Streamlit Web Application**: Main user interface
- **Background Processing**: Audio enhancement and LLM processing
- **Database**: SQLite for configuration and data storage
- **External Dependencies**: Ollama, GPU acceleration, audio processing libraries
- **File Storage**: Local file system for audio processing

### Containerization Requirements
- **GPU Support**: CUDA acceleration for audio enhancement
- **Volume Persistence**: Configuration, database, and processed files
- **Network Connectivity**: External API access (OpenAI, SermonAudio)
- **Service Discovery**: Ollama and other services
- **Scalability**: Horizontal scaling for processing workloads

## Phase 1: Base Containerization (Week 1)

### 1.1 Multi-Stage Dockerfile Design

```dockerfile
# Dockerfile
# Multi-stage build for optimized container size

# Stage 1: Base dependencies
FROM nvidia/cuda:12.1-devel-ubuntu22.04 AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    curl \
    wget \
    git \
    ffmpeg \
    libsndfile1 \
    libasound2-dev \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN useradd -m -u 1000 sermonapp && \
    mkdir -p /app /data /models /logs && \
    chown -R sermonapp:sermonapp /app /data /models /logs

# Stage 2: Python dependencies
FROM base AS python-deps

# Install UV package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy requirements first for better caching
COPY requirements/ requirements/
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv venv /app/venv && \
    . /app/venv/bin/activate && \
    uv pip install -r requirements/requirements.txt && \
    uv pip install -r requirements/requirements-gpu.txt

# Stage 3: Application code
FROM python-deps AS app

# Copy application code
COPY --chown=sermonapp:sermonapp . /app/

# Create necessary directories
RUN mkdir -p /app/processed_sermons \
             /app/analytics_cache \
             /app/analytics_vector_db \
             /app/api_cache \
             /app/logs \
             /app/config_backups

# Set proper permissions
RUN chown -R sermonapp:sermonapp /app && \
    chmod +x /app/start_server.sh

# Switch to application user
USER sermonapp

# Expose ports
EXPOSE 8501 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/healthz || exit 1

# Default command
CMD ["/app/start_server.sh"]
```

### 1.2 Environment-Specific Configurations

```dockerfile
# Dockerfile.dev - Development version
FROM app AS dev

USER root

# Install development tools
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install development Python packages
RUN . /app/venv/bin/activate && \
    uv pip install pytest pytest-cov black ruff mypy

USER sermonapp

# Development command with hot reload
CMD ["streamlit", "run", "streamlit_app.py", "--server.fileWatcherType", "poll"]
```

```dockerfile
# Dockerfile.prod - Production version
FROM app AS prod

# Remove development files
RUN rm -rf /app/tests /app/Test* /app/copilot-plans /app/.git* /app/examples

# Production optimizations
ENV PYTHONOPTIMIZE=2
ENV PYTHONDONTWRITEBYTECODE=1

# Production startup script
CMD ["/app/docker/start_production.sh"]
```

### 1.3 Container Startup Scripts

```bash
#!/bin/bash
# docker/start_production.sh
set -e

echo "🚀 Starting SermonAudio Processor (Production Mode)"

# Wait for external dependencies
echo "⏳ Waiting for external services..."
python /app/docker/wait_for_services.py

# Initialize database if needed
echo "🗄️ Initializing database..."
python -c "
from src.database import DatabaseManager
db = DatabaseManager()
db.initialize_database()
print('✅ Database initialized')
"

# Run database migrations
echo "🔄 Running database migrations..."
python /app/tools/migrate_config.py

# Start background job processor
echo "⚙️ Starting background job processor..."
python /app/src/job_queue.py --daemon &

# Start performance monitor
echo "📊 Starting performance monitor..."
python /app/src/performance_monitor.py --daemon &

# Start main application
echo "🌐 Starting Streamlit application..."
exec streamlit run streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
```

```python
# docker/wait_for_services.py
import time
import requests
import os
import sys
from typing import List, Tuple

def wait_for_service(host: str, port: int, timeout: int = 120) -> bool:
    """Wait for a service to become available."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"http://{host}:{port}/api/tags", timeout=5)
            if response.status_code == 200:
                return True
        except (requests.RequestException, ConnectionError):
            pass
        
        time.sleep(2)
    
    return False

def check_required_services() -> List[Tuple[str, bool]]:
    """Check all required external services."""
    services = []
    
    # Ollama service
    ollama_host = os.getenv('OLLAMA_HOST', 'ollama').replace('http://', '').split(':')[0]
    ollama_port = int(os.getenv('OLLAMA_PORT', '11434'))
    
    print(f"Checking Ollama at {ollama_host}:{ollama_port}...")
    ollama_available = wait_for_service(ollama_host, ollama_port)
    services.append(("Ollama", ollama_available))
    
    # Database (if external)
    db_host = os.getenv('DATABASE_HOST')
    if db_host:
        db_port = int(os.getenv('DATABASE_PORT', '5432'))
        print(f"Checking Database at {db_host}:{db_port}...")
        db_available = wait_for_service(db_host, db_port)
        services.append(("Database", db_available))
    
    return services

if __name__ == "__main__":
    print("🔍 Checking external service dependencies...")
    
    services = check_required_services()
    
    all_available = True
    for service_name, available in services:
        status = "✅" if available else "❌"
        print(f"{status} {service_name}: {'Available' if available else 'Unavailable'}")
        if not available:
            all_available = False
    
    if not all_available:
        print("❌ Some required services are unavailable. Exiting...")
        sys.exit(1)
    
    print("✅ All required services are available!")
```

## Phase 2: Service Orchestration (Week 2)

### 2.1 Docker Compose Configuration

```yaml
# docker-compose.yml - Complete stack
version: '3.8'

services:
  # Main application
  sermon-processor:
    build:
      context: .
      dockerfile: Dockerfile
      target: prod
    container_name: sermon-processor
    restart: unless-stopped
    ports:
      - "8501:8501"
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
      - OLLAMA_HOST=http://ollama:11434
      - DATABASE_URL=sqlite:///data/sermon_processor.db
      - CUDA_VISIBLE_DEVICES=0
    volumes:
      - sermon_data:/data
      - sermon_models:/models
      - sermon_logs:/app/logs
      - sermon_config:/app/config_backups
      - /tmp:/tmp
    depends_on:
      - ollama
      - redis
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - sermon_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s

  # Ollama service for local LLM inference
  ollama:
    image: ollama/ollama:latest
    container_name: sermon-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    environment:
      - OLLAMA_HOST=0.0.0.0
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - sermon_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Redis for job queue and caching
  redis:
    image: redis:7-alpine
    container_name: sermon-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --maxmemory 1gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    networks:
      - sermon_network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  # PostgreSQL (optional, for production)
  postgres:
    image: postgres:15-alpine
    container_name: sermon-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=sermon_processor
      - POSTGRES_USER=sermon_user
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    secrets:
      - postgres_password
    networks:
      - sermon_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sermon_user -d sermon_processor"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Nginx reverse proxy
  nginx:
    image: nginx:alpine
    container_name: sermon-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./docker/nginx/ssl:/etc/nginx/ssl
      - nginx_logs:/var/log/nginx
    depends_on:
      - sermon-processor
    networks:
      - sermon_network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Monitoring and observability
  prometheus:
    image: prom/prometheus:latest
    container_name: sermon-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./docker/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'
    networks:
      - sermon_network

  grafana:
    image: grafana/grafana:latest
    container_name: sermon-grafana
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_password
    volumes:
      - grafana_data:/var/lib/grafana
      - ./docker/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./docker/grafana/datasources:/etc/grafana/provisioning/datasources
    secrets:
      - grafana_password
    depends_on:
      - prometheus
    networks:
      - sermon_network

# Development override
  sermon-processor-dev:
    extends:
      service: sermon-processor
    build:
      target: dev
    environment:
      - ENVIRONMENT=development
      - DEBUG=true
    volumes:
      - .:/app
      - sermon_data_dev:/data
    ports:
      - "8501:8501"
      - "8000:8000"
      - "5678:5678"  # Debug port
    command: ["streamlit", "run", "streamlit_app.py", "--server.fileWatcherType", "poll"]
    profiles:
      - dev

volumes:
  sermon_data:
  sermon_models:
  sermon_logs:
  sermon_config:
  ollama_data:
  redis_data:
  postgres_data:
  nginx_logs:
  prometheus_data:
  grafana_data:
  sermon_data_dev:

networks:
  sermon_network:
    driver: bridge

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  grafana_password:
    file: ./secrets/grafana_password.txt
```

### 2.2 Development Compose Override

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  sermon-processor:
    build:
      target: dev
    environment:
      - ENVIRONMENT=development
      - DEBUG=true
      - WATCHDOG_ENABLED=true
    volumes:
      - .:/app
      - sermon_data_dev:/data
    ports:
      - "8501:8501"
      - "8000:8000"
      - "5678:5678"  # Debug port
    command: ["streamlit", "run", "streamlit_app.py", "--server.fileWatcherType", "poll"]

  # Development tools
  jupyter:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: sermon-jupyter
    ports:
      - "8888:8888"
    environment:
      - JUPYTER_ENABLE_LAB=yes
    volumes:
      - .:/app
      - sermon_data_dev:/data
    command: ["jupyter", "lab", "--ip=0.0.0.0", "--allow-root", "--no-browser"]
    networks:
      - sermon_network
    profiles:
      - dev

volumes:
  sermon_data_dev:
```

### 2.3 Production Compose Configuration

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  sermon-processor:
    build:
      target: prod
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://sermon_user:${POSTGRES_PASSWORD}@postgres:5432/sermon_processor
    deploy:
      replicas: 2
      update_config:
        parallelism: 1
        delay: 10s
        failure_action: rollback
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  # Load balancer for multiple app instances
  haproxy:
    image: haproxy:alpine
    container_name: sermon-haproxy
    ports:
      - "80:80"
      - "443:443"
      - "8404:8404"  # Stats
    volumes:
      - ./docker/haproxy/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg
      - ./docker/haproxy/ssl:/etc/ssl/certs
    depends_on:
      - sermon-processor
    networks:
      - sermon_network

  # Log aggregation
  elasticsearch:
    image: elasticsearch:8.10.0
    container_name: sermon-elasticsearch
    environment:
      - discovery.type=single-node
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    networks:
      - sermon_network

  logstash:
    image: logstash:8.10.0
    container_name: sermon-logstash
    volumes:
      - ./docker/logstash/logstash.conf:/usr/share/logstash/pipeline/logstash.conf
      - sermon_logs:/logs
    depends_on:
      - elasticsearch
    networks:
      - sermon_network

  kibana:
    image: kibana:8.10.0
    container_name: sermon-kibana
    ports:
      - "5601:5601"
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
    depends_on:
      - elasticsearch
    networks:
      - sermon_network

volumes:
  elasticsearch_data:
```

## Phase 3: Production Deployment (Week 3)

### 3.1 Kubernetes Deployment

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sermon-processor
  labels:
    name: sermon-processor

---
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sermon-config
  namespace: sermon-processor
data:
  ENVIRONMENT: "production"
  OLLAMA_HOST: "http://ollama-service:11434"
  REDIS_URL: "redis://redis-service:6379"
  LOG_LEVEL: "INFO"

---
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: sermon-secrets
  namespace: sermon-processor
type: Opaque
data:
  # Base64 encoded secrets
  sermonaudio-api-key: # echo -n 'your-api-key' | base64
  openai-api-key: # echo -n 'your-openai-key' | base64
  postgres-password: # echo -n 'your-postgres-password' | base64

---
# k8s/persistent-volume.yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: sermon-data-pv
spec:
  capacity:
    storage: 100Gi
  accessModes:
    - ReadWriteMany
  persistentVolumeReclaimPolicy: Retain
  storageClassName: nfs
  nfs:
    server: nfs.example.com
    path: /exports/sermon-data

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: sermon-data-pvc
  namespace: sermon-processor
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 100Gi
  storageClassName: nfs

---
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sermon-processor
  namespace: sermon-processor
spec:
  replicas: 3
  selector:
    matchLabels:
      app: sermon-processor
  template:
    metadata:
      labels:
        app: sermon-processor
    spec:
      containers:
      - name: sermon-processor
        image: sermon-processor:latest
        ports:
        - containerPort: 8501
        - containerPort: 8000
        env:
        - name: SERMONAUDIO_API_KEY
          valueFrom:
            secretKeyRef:
              name: sermon-secrets
              key: sermonaudio-api-key
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: sermon-secrets
              key: openai-api-key
        envFrom:
        - configMapRef:
            name: sermon-config
        volumeMounts:
        - name: sermon-data
          mountPath: /data
        - name: sermon-models
          mountPath: /models
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
            nvidia.com/gpu: 1
          limits:
            memory: "4Gi"
            cpu: "2000m"
            nvidia.com/gpu: 1
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8501
          initialDelaySeconds: 120
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8501
          initialDelaySeconds: 60
          periodSeconds: 10
      volumes:
      - name: sermon-data
        persistentVolumeClaim:
          claimName: sermon-data-pvc
      - name: sermon-models
        emptyDir:
          sizeLimit: 50Gi

---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: sermon-processor-service
  namespace: sermon-processor
spec:
  selector:
    app: sermon-processor
  ports:
  - name: web
    port: 80
    targetPort: 8501
  - name: api
    port: 8000
    targetPort: 8000
  type: ClusterIP

---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sermon-processor-ingress
  namespace: sermon-processor
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
spec:
  tls:
  - hosts:
    - sermon.example.com
    secretName: sermon-processor-tls
  rules:
  - host: sermon.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: sermon-processor-service
            port:
              number: 80

---
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: sermon-processor-hpa
  namespace: sermon-processor
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: sermon-processor
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### 3.2 Helm Chart Structure

```yaml
# helm/sermon-processor/Chart.yaml
apiVersion: v2
name: sermon-processor
description: A Helm chart for SermonAudio Processor
type: application
version: 1.0.0
appVersion: "1.0.0"
dependencies:
  - name: postgresql
    version: "12.1.2"
    repository: "https://charts.bitnami.com/bitnami"
    condition: postgresql.enabled
  - name: redis
    version: "17.3.7"
    repository: "https://charts.bitnami.com/bitnami"
    condition: redis.enabled

---
# helm/sermon-processor/values.yaml
# Default values for sermon-processor
replicaCount: 2

image:
  repository: sermon-processor
  pullPolicy: IfNotPresent
  tag: "latest"

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations: {}

podSecurityContext:
  fsGroup: 1000

securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
    - ALL
  readOnlyRootFilesystem: false
  runAsNonRoot: true
  runAsUser: 1000

service:
  type: ClusterIP
  port: 80
  targetPort: 8501

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
  hosts:
    - host: sermon.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: sermon-processor-tls
      hosts:
        - sermon.example.com

resources:
  limits:
    cpu: 2000m
    memory: 4Gi
    nvidia.com/gpu: 1
  requests:
    cpu: 1000m
    memory: 2Gi
    nvidia.com/gpu: 1

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

nodeSelector:
  gpu: "true"

tolerations:
  - key: "nvidia.com/gpu"
    operator: "Exists"
    effect: "NoSchedule"

affinity: {}

persistence:
  enabled: true
  storageClass: "nfs"
  accessMode: ReadWriteMany
  size: 100Gi

# External services
postgresql:
  enabled: true
  auth:
    postgresPassword: "sermon-postgres-password"
    username: "sermon_user"
    password: "sermon-user-password"
    database: "sermon_processor"

redis:
  enabled: true
  auth:
    enabled: false

# Application configuration
config:
  environment: "production"
  logLevel: "INFO"
  debug: false

# Secrets (override in values-prod.yaml)
secrets:
  sermonAudioApiKey: ""
  openaiApiKey: ""
  anthropicApiKey: ""
  xaiApiKey: ""
```

## Phase 4: Operational Excellence (Week 4)

### 4.1 Monitoring and Observability

```yaml
# docker/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

scrape_configs:
  - job_name: 'sermon-processor'
    static_configs:
      - targets: ['sermon-processor:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  - job_name: 'ollama'
    static_configs:
      - targets: ['ollama:11434']
    metrics_path: '/metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093
```

```python
# src/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import functools
import time

# Application metrics
sermon_processing_total = Counter('sermon_processing_total', 'Total sermons processed', ['status', 'method'])
sermon_processing_duration = Histogram('sermon_processing_duration_seconds', 'Time spent processing sermons')
active_users = Gauge('active_users_total', 'Number of active users')
gpu_utilization = Gauge('gpu_utilization_percent', 'GPU utilization percentage')
memory_usage = Gauge('memory_usage_bytes', 'Memory usage in bytes')

def track_processing_time(func):
    """Decorator to track function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            sermon_processing_total.labels(status='success', method=func.__name__).inc()
            return result
        except Exception as e:
            sermon_processing_total.labels(status='error', method=func.__name__).inc()
            raise
        finally:
            sermon_processing_duration.observe(time.time() - start_time)
    return wrapper

def start_metrics_server(port: int = 8000):
    """Start Prometheus metrics server."""
    start_http_server(port)
    print(f"📊 Metrics server started on port {port}")
```

### 4.2 Logging and Tracing

```python
# src/logging/structured_logging.py
import logging
import json
import sys
from datetime import datetime
from typing import Dict, Any
import traceback

class StructuredFormatter(logging.Formatter):
    """Structured JSON logging formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception information if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = record.user_id
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = record.request_id
        if hasattr(record, 'sermon_id'):
            log_entry['sermon_id'] = record.sermon_id
        
        return json.dumps(log_entry)

def setup_logging(level: str = "INFO", service_name: str = "sermon-processor"):
    """Set up structured logging."""
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove default handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Add structured handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    
    # Set service name
    logging.getLogger().service_name = service_name
    
    return logger

# Usage example
logger = setup_logging()

def log_sermon_processing(sermon_id: str, user_id: str):
    """Example of contextual logging."""
    extra_context = {
        'sermon_id': sermon_id,
        'user_id': user_id
    }
    
    logger.info("Starting sermon processing", extra=extra_context)
```

### 4.3 Backup and Disaster Recovery

```bash
#!/bin/bash
# docker/backup/backup_script.sh

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="sermon-processor"

echo "🔄 Starting backup process..."

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup application data
echo "📁 Backing up application data..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR/$DATE":/backup \
    alpine:latest \
    tar czf /backup/sermon_data.tar.gz /data

# Backup database
echo "🗄️ Backing up database..."
docker exec sermon-postgres pg_dump -U sermon_user sermon_processor | gzip > "$BACKUP_DIR/$DATE/database.sql.gz"

# Backup configuration
echo "⚙️ Backing up configuration..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR/$DATE":/backup \
    alpine:latest \
    tar czf /backup/config.tar.gz /app/config_backups

# Create backup manifest
echo "📝 Creating backup manifest..."
cat > "$BACKUP_DIR/$DATE/manifest.json" << EOF
{
    "backup_date": "$DATE",
    "container_name": "$CONTAINER_NAME",
    "files": [
        "sermon_data.tar.gz",
        "database.sql.gz",
        "config.tar.gz"
    ],
    "size": "$(du -sh $BACKUP_DIR/$DATE | cut -f1)"
}
EOF

# Cleanup old backups (keep last 7 days)
echo "🧹 Cleaning up old backups..."
find "$BACKUP_DIR" -type d -name "*_*" -mtime +7 -exec rm -rf {} \;

echo "✅ Backup completed: $BACKUP_DIR/$DATE"
```

```bash
#!/bin/bash
# docker/backup/restore_script.sh

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup_date>"
    echo "Available backups:"
    ls -la /backups/
    exit 1
fi

BACKUP_DATE=$1
BACKUP_DIR="/backups/$BACKUP_DATE"
CONTAINER_NAME="sermon-processor"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "❌ Backup directory not found: $BACKUP_DIR"
    exit 1
fi

echo "🔄 Starting restore process from $BACKUP_DATE..."

# Stop application
echo "⏹️ Stopping application..."
docker-compose stop sermon-processor

# Restore database
echo "🗄️ Restoring database..."
zcat "$BACKUP_DIR/database.sql.gz" | docker exec -i sermon-postgres psql -U sermon_user -d sermon_processor

# Restore application data
echo "📁 Restoring application data..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR":/backup \
    alpine:latest \
    sh -c "cd / && tar xzf /backup/sermon_data.tar.gz"

# Restore configuration
echo "⚙️ Restoring configuration..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR":/backup \
    alpine:latest \
    sh -c "cd / && tar xzf /backup/config.tar.gz"

# Start application
echo "▶️ Starting application..."
docker-compose start sermon-processor

echo "✅ Restore completed from $BACKUP_DATE"
```

## Implementation Timeline

### Week 1: Base Containerization
- [ ] Create multi-stage Dockerfiles for development and production
- [ ] Implement container startup scripts and health checks
- [ ] Set up basic Docker Compose configuration
- [ ] Test local container deployment

### Week 2: Service Orchestration
- [ ] Complete Docker Compose stack with all services
- [ ] Implement service discovery and networking
- [ ] Set up Redis for job queuing and caching
- [ ] Configure Nginx reverse proxy

### Week 3: Production Deployment
- [ ] Create Kubernetes manifests and Helm charts
- [ ] Implement horizontal pod autoscaling
- [ ] Set up persistent storage and secrets management
- [ ] Configure ingress and load balancing

### Week 4: Operational Excellence
- [ ] Implement comprehensive monitoring and alerting
- [ ] Set up structured logging and tracing
- [ ] Create backup and disaster recovery procedures
- [ ] Performance optimization and security hardening

## Benefits of Containerization

### Development Benefits
- **Consistent Environments**: Identical development, testing, and production environments
- **Faster Onboarding**: New developers can start immediately with `docker-compose up`
- **Dependency Isolation**: No conflicts with host system dependencies

### Production Benefits
- **Scalability**: Horizontal scaling with load balancing
- **Reliability**: Health checks, auto-restart, and rolling updates
- **Resource Efficiency**: Optimized resource allocation and utilization

### Operational Benefits
- **Simplified Deployment**: Single command deployment with rollback capability
- **Monitoring**: Comprehensive observability with metrics, logs, and traces
- **Backup and Recovery**: Automated backup procedures with point-in-time recovery

This containerization plan ensures the SermonAudio Processor can be deployed reliably at scale while maintaining operational excellence and development velocity.
