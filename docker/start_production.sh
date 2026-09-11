#!/bin/bash
# docker/start_production.sh
set -e

echo "Starting SermonPilot"

VARIANT="${SERMONPILOT_VARIANT:-unknown}"
echo "Variant: ${VARIANT}"
if [ "${VARIANT}" != "unknown" ] && [ -f "/app/config/templates/${VARIANT}.yaml" ]; then
    echo "Config template: /app/config/templates/${VARIANT}.yaml (import from the UI config page or point SA_UPDATER_CONFIG at it)"
fi

# Non-fatal GPU report. Missing torch, missing onnxruntime, or a CPU-only
# host must never stop startup, so every failure prints one line and the
# call is guarded against set -e.
python - <<'PYEOF' || true
try:
    import torch
except Exception as exc:
    print(f"GPU: torch unavailable ({exc})")
else:
    try:
        available = torch.cuda.is_available()
    except Exception as exc:
        print(f"GPU: torch.cuda.is_available() failed ({exc})")
    else:
        if available:
            try:
                name = torch.cuda.get_device_name(0)
            except Exception:
                name = "unknown device"
            print(f"GPU: torch.cuda.is_available()=True ({name})")
        else:
            print("GPU: torch.cuda.is_available()=False")

try:
    import onnxruntime as ort
except Exception as exc:
    print(f"ORT providers: unavailable ({exc})")
else:
    try:
        providers = ort.get_available_providers()
    except Exception as exc:
        print(f"ORT providers: unavailable ({exc})")
    else:
        print(f"ORT providers: {providers}")
        if "CUDAExecutionProvider" in providers:
            # Wheel build lists the provider, but the EP only engages when the
            # CUDA user-space libraries actually load. dlopen is the honest check.
            import ctypes

            for lib in ("libcudart.so.12", "libcublas.so.12", "libcudnn.so.9"):
                try:
                    ctypes.CDLL(lib)
                    print(f"CUDA lib {lib}: loadable")
                except OSError as exc:
                    print(f"CUDA lib {lib}: NOT loadable ({exc})")
PYEOF

# Graceful shutdown handler
cleanup() {
    echo "Shutting down gracefully..."
    if [ -n "$STREAMLIT_PID" ]; then
        kill -TERM "$STREAMLIT_PID" 2>/dev/null
        wait "$STREAMLIT_PID" 2>/dev/null
    fi
    echo "Shutdown complete"
    exit 0
}
trap cleanup SIGTERM SIGINT

# Ensure persistent data directories exist. Fresh named volumes inherit the
# image ownership, but volumes created by older images can surface root-owned
# and shadow the build-time setup.
VOLUME_DIRS="/data /models /app/api_cache /app/processed_sermons /app/logs /home/sermonapp/.cache"
mkdir -p ${VOLUME_DIRS} || true

if [ "$(id -u)" = "0" ]; then
    chown -R 1000:1000 ${VOLUME_DIRS} || true
else
    UNWRITABLE=""
    for dir in ${VOLUME_DIRS}; do
        if [ ! -w "$dir" ]; then
            UNWRITABLE="${UNWRITABLE} ${dir}"
        fi
    done
    if [ -n "$UNWRITABLE" ]; then
        echo "WARNING: these paths are not writable by user sermonapp (uid $(id -u)):${UNWRITABLE}"
        echo "  SQLite and file caches under them will fail until ownership is repaired."
        echo "  Repair on the host, for example:"
        echo "    docker run --rm -v <project>_sermon_data:/data alpine chown -R 1000:1000 /data"
    fi
fi

# Initialize database if needed
echo "Initializing database..."
DB_URL="${DATABASE_URL:-sqlite:///data/sermon_processor.db}"
case "$DB_URL" in
    sqlite:///*)
        DB_PATH="${DB_URL#sqlite:///}"
        case "$DB_PATH" in
            /*) ;;
            *) DB_PATH="/$DB_PATH" ;;
        esac
        echo "Database: sqlite at ${DB_PATH}"
        ;;
    *)
        echo "Database URL: $(printf '%s' "$DB_URL" | sed -E 's#(://[^:/@]+:)[^@]*@#\1***@#')"
        ;;
esac
python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/ui')
try:
    from ui.database import SermonRepository
    repo = SermonRepository()
    print('Database ready')
except Exception as e:
    print(f'Database initialization warning: {e}')
"

# Start main application
echo "Starting Streamlit application..."
streamlit run streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.maxUploadSize=2000 \
    --browser.gatherUsageStats=false &
STREAMLIT_PID=$!

# Wait for Streamlit process
wait $STREAMLIT_PID
