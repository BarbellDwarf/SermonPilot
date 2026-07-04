ARG GPU_BACKEND=cuda

FROM ubuntu:22.04 AS base-cpu

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS base-cuda

FROM rocm/dev-ubuntu-22.04:6.2 AS base-rocm

FROM base-${GPU_BACKEND} AS base

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

RUN python3.11 -m venv /app/venv

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src:/app/ui"

RUN useradd -m -u 1000 sermonapp && \
    mkdir -p /app /data /models /logs && \
    chown -R sermonapp:sermonapp /app /data /models /logs

WORKDIR /app

COPY requirements/ requirements/
COPY pyproject.toml ./

RUN pip install --no-cache-dir -r requirements/requirements.txt && \
    if [ "$GPU_BACKEND" = "cuda" ]; then \
        pip install --no-cache-dir --force-reinstall torch==2.1.1+cu121 torchaudio==2.1.1+cu121 torchvision==0.16.1+cu121 \
            --extra-index-url https://download.pytorch.org/whl/cu121; \
    elif [ "$GPU_BACKEND" = "rocm" ]; then \
        pip install --no-cache-dir --force-reinstall torch==2.1.1+rocm6.2 torchaudio==2.1.1+rocm6.2 torchvision==0.16.1+rocm6.2 \
            --extra-index-url https://download.pytorch.org/whl/rocm6.2; \
    else \
        pip install --no-cache-dir --force-reinstall torch==2.1.1 torchaudio==2.1.1 torchvision==0.16.1 \
            --extra-index-url https://download.pytorch.org/whl/cpu; \
    fi && \
    pip install --no-cache-dir 'numpy>=1.26.2,<2.0.0'

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
