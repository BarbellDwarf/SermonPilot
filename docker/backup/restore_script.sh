#!/bin/bash
# docker/backup/restore_script.sh

set -e

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup_date>"
    echo "Available backups:"
    ls -la /backups/ 2>/dev/null || echo "No backups found"
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
docker compose stop sermon-processor

# Restore database
if [ -f "$BACKUP_DIR/database.sql.gz" ]; then
    if docker ps | grep -q sermon-postgres; then
        echo "🗄️ Restoring PostgreSQL database..."
        zcat "$BACKUP_DIR/database.sql.gz" | docker exec -i sermon-postgres psql -U sermon_user -d sermon_processor
    else
        echo "⚠️ PostgreSQL not running, skipping database restore"
    fi
elif [ -f "$BACKUP_DIR/sermon_processor.db" ]; then
    echo "📂 Restoring SQLite database..."
    docker run --rm \
        --volumes-from $CONTAINER_NAME \
        -v "$BACKUP_DIR":/backup \
        alpine:latest \
        cp /backup/sermon_processor.db /data/
fi

# Restore application data
if [ -f "$BACKUP_DIR/sermon_data.tar.gz" ]; then
    echo "📁 Restoring application data..."
    docker run --rm \
        --volumes-from $CONTAINER_NAME \
        -v "$BACKUP_DIR":/backup \
        alpine:latest \
        sh -c "cd / && tar xzf /backup/sermon_data.tar.gz"
fi

# Restore configuration
if [ -f "$BACKUP_DIR/config.tar.gz" ]; then
    echo "⚙️ Restoring configuration..."
    docker run --rm \
        --volumes-from $CONTAINER_NAME \
        -v "$BACKUP_DIR":/backup \
        alpine:latest \
        sh -c "cd / && tar xzf /backup/config.tar.gz"
fi

# Start application
echo "▶️ Starting application..."
docker compose start sermon-processor

echo "✅ Restore completed from $BACKUP_DATE"