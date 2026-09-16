#!/bin/bash
# docker/start_production.sh
set -e

echo "🚀 Starting SermonPilot"

# Graceful shutdown handler
cleanup() {
    echo "🛑 Shutting down gracefully..."
    if [ -n "$UVICORN_PID" ]; then
        kill -TERM "$UVICORN_PID" 2>/dev/null
        wait "$UVICORN_PID" 2>/dev/null
    fi
    if [ -n "$STREAMLIT_PID" ]; then
        kill -TERM "$STREAMLIT_PID" 2>/dev/null
        wait "$STREAMLIT_PID" 2>/dev/null
    fi
    echo "✅ Shutdown complete"
    exit 0
}
trap cleanup SIGTERM SIGINT

# Ensure persistent data directories exist
mkdir -p /data /app/processed_sermons /app/logs

# Initialize database if needed
echo "🗄️ Initializing database..."
python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/ui')
try:
    from ui.database import SermonRepository
    repo = SermonRepository()
    print('✅ Database ready')
except Exception as e:
    print(f'⚠️ Database initialization warning: {e}')
"

# Start main application
echo "🌐 Starting Streamlit application..."
streamlit run streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.maxUploadSize=${STREAMLIT_SERVER_MAX_UPLOAD_SIZE:-30720} \
    --browser.gatherUsageStats=false &
STREAMLIT_PID=$!

# Start read-only web API + SPA (opt out with SERMONPILOT_WEB_API=0)
if [ "${SERMONPILOT_WEB_API:-}" != "0" ]; then
    echo "🌐 Starting web API..."
    uvicorn server.api.app:app --host 0.0.0.0 --port "${SERMONPILOT_WEB_PORT:-8504}" &
    UVICORN_PID=$!
fi

# Wait for background processes
wait $STREAMLIT_PID ${UVICORN_PID:-}
