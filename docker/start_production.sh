#!/bin/bash
# docker/start_production.sh
set -e

echo "🚀 Starting SermonAudio Processor"

# Wait for external dependencies (Ollama, Redis if configured)
if [ -n "$OLLAMA_HOST" ] || [ -n "$REDIS_HOST" ]; then
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
exec streamlit run streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.maxUploadSize=2000 \
    --browser.gatherUsageStats=false
