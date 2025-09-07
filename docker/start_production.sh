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
import sys
sys.path.insert(0, '/app/src')
try:
    from database import DatabaseManager
    db = DatabaseManager()
    db.initialize_database()
    print('✅ Database initialized')
except Exception as e:
    print(f'⚠️ Database initialization warning: {e}')
"

# Run database migrations if they exist
if [ -f "/app/tools/migrate_config.py" ]; then
    echo "🔄 Running database migrations..."
    python /app/tools/migrate_config.py
fi

# Start background job processor if it exists
if [ -f "/app/src/job_queue.py" ]; then
    echo "⚙️ Starting background job processor..."
    python /app/src/job_queue.py --daemon &
fi

# Start performance monitor if it exists
if [ -f "/app/src/performance_monitor.py" ]; then
    echo "📊 Starting performance monitor..."
    python /app/src/performance_monitor.py --daemon &
fi

# Start main application
echo "🌐 Starting Streamlit application..."
exec streamlit run streamlit_app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false