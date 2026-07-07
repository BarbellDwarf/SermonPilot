#!/bin/bash
# docker/start_production.sh
set -e

echo "🚀 Starting SermonPilot"

# Graceful shutdown handler
cleanup() {
    echo "🛑 Shutting down gracefully..."
    if [ -n "$STREAMLIT_PID" ]; then
        kill -TERM "$STREAMLIT_PID" 2>/dev/null
        wait "$STREAMLIT_PID" 2>/dev/null
    fi
    echo "✅ Shutdown complete"
    exit 0
}
trap cleanup SIGTERM SIGINT

# Wait for external dependencies (database if configured)
if [ -n "$DATABASE_HOST" ]; then
    echo "⏳ Waiting for external services..."
    python /app/docker/wait_for_services.py
fi

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
    --server.maxUploadSize=2000 \
    --browser.gatherUsageStats=false &
STREAMLIT_PID=$!

# Wait for Streamlit process
wait $STREAMLIT_PID
