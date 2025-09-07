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
    pkg-config \
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
             /app/config_backups \
             /app/docker

# Set proper permissions
RUN chown -R sermonapp:sermonapp /app && \
    chmod +x /app/start_server.sh && \
    chmod +x /app/docker/start_production.sh 2>/dev/null || true

# Switch to application user
USER sermonapp

# Set Python path
ENV PYTHONPATH="/app:/app/src:$PYTHONPATH"
ENV PATH="/app/venv/bin:$PATH"

# Expose ports
EXPOSE 8501 8000

# Health check - check if Streamlit is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/ || exit 1

# Default command
CMD ["/app/start_server.sh"]