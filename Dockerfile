ARG GPU_BACKEND=cpu

FROM ubuntu:22.04 AS base-cpu

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04 AS base-cuda

FROM rocm/dev-ubuntu-22.04:7.1 AS base-rocm

FROM base-${GPU_BACKEND} AS base

# Pre-FROM args must be redeclared to be visible inside the stage;
# this also makes the requirements selection below actually branch.
ARG GPU_BACKEND
ARG SERMONPILOT_VARIANT=${GPU_BACKEND}

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

RUN python3.11 -m venv /app/venv

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src:/app/ui"
ENV SERMONPILOT_VARIANT=${SERMONPILOT_VARIANT}

RUN useradd -m -u 1000 sermonapp && \
    mkdir -p /app /data /models /logs /home/sermonapp/.cache && \
    chown -R sermonapp:sermonapp /app /data /models /logs /home/sermonapp/.cache

WORKDIR /app

COPY requirements/ requirements/
COPY pyproject.toml ./

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# uv's default index strategy takes a package from the first index that has it;
# the PyTorch cu124 index carries stale shadows of PyPI packages (e.g. requests),
# so best-match across indexes is required for the GPU requirement sets.
ENV UV_INDEX_STRATEGY=unsafe-best-match

# Install core + GPU-specific dependencies
RUN if [ "$GPU_BACKEND" = "cuda" ]; then \
        uv pip install --no-cache-dir -r requirements/requirements-gpu.txt && \
        uv pip install --no-cache-dir "onnxruntime-gpu>=1.22.1"; \
    elif [ "$GPU_BACKEND" = "rocm" ]; then \
        uv pip install --no-cache-dir -r requirements/requirements-rocm.txt; \
    else \
        uv pip install --no-cache-dir -r requirements/requirements.txt; \
    fi

COPY --chown=sermonapp:sermonapp . /app/

RUN mkdir -p /app/processed_sermons \
             /app/analytics_cache \
             /app/analytics_vector_db \
             /app/api_cache \
             /app/logs \
             /app/config_backups && \
    chown -R sermonapp:sermonapp /app && \
    chmod +x /app/docker/start_production.sh

USER sermonapp

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/ || exit 1

CMD ["/app/docker/start_production.sh"]
