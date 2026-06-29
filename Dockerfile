# Dockerfile
# Multi-stage build with GPU backend selection
# Build with: docker build --build-arg GPU_BACKEND=cuda -t sermon-processor:cuda .
# Options: cuda, rocm, cpu

ARG GPU_BACKEND=cuda

# ============================================================
# Stage 1: Base image selection based on GPU backend
# ============================================================
FROM ubuntu:22.04 AS base-cpu

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS base-cuda

FROM rocm/dev-ubuntu-22.04:6.2 AS base-rocm

FROM base-${GPU_BACKEND} AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    curl \
    wget \
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

# ============================================================
# Stage 2: Python dependencies
# ============================================================
FROM base AS python-deps

# Install UV package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Copy requirements first for better caching
COPY requirements/ requirements/
COPY pyproject.toml uv.lock ./

# Install Python dependencies based on GPU backend
RUN . /app/venv/bin/activate 2>/dev/null || python3.11 -m venv /app/venv && \
    . /app/venv/bin/activate && \
    uv pip install -r requirements/requirements.txt && \
    if [ "$GPU_BACKEND" = "cuda" ]; then \
        uv pip install -r requirements/requirements-gpu.txt; \
    elif [ "$GPU_BACKEND" = "rocm" ]; then \
        uv pip install -r requirements/requirements-rocm.txt; \
    else \
        uv pip install -r requirements/requirements-cpu.txt; \
    fi

# ============================================================
# Stage 3: Application code
# ============================================================
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
    chmod +x /app/docker/start_production.sh

# Switch to application user
USER sermonapp

# Set Python path
ENV PYTHONPATH="/app:/app/src:/app/ui:$PYTHONPATH"
ENV PATH="/app/venv/bin:$PATH"

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/ || exit 1

# Default command
CMD ["/app/docker/start_production.sh"]
