#!/bin/bash
# docker/backup/backup_script.sh

set -e

BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="sermon-processor"

echo "🔄 Starting backup process..."

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup application data
echo "📁 Backing up application data..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR/$DATE":/backup \
    alpine:latest \
    tar czf /backup/sermon_data.tar.gz /data

# Backup database if PostgreSQL is running
if docker ps | grep -q sermon-postgres; then
    echo "🗄️ Backing up PostgreSQL database..."
    docker exec sermon-postgres pg_dump -U sermon_user sermon_processor | gzip > "$BACKUP_DIR/$DATE/database.sql.gz"
else
    echo "📂 Backing up SQLite database..."
    docker run --rm \
        --volumes-from $CONTAINER_NAME \
        -v "$BACKUP_DIR/$DATE":/backup \
        alpine:latest \
        sh -c "if [ -f /data/sermon_processor.db ]; then cp /data/sermon_processor.db /backup/; fi"
fi

# Backup configuration
echo "⚙️ Backing up configuration..."
docker run --rm \
    --volumes-from $CONTAINER_NAME \
    -v "$BACKUP_DIR/$DATE":/backup \
    alpine:latest \
    tar czf /backup/config.tar.gz /app/config_backups /app/*.yaml 2>/dev/null || true

# Create backup manifest
echo "📝 Creating backup manifest..."
cat > "$BACKUP_DIR/$DATE/manifest.json" << EOF
{
    "backup_date": "$DATE",
    "container_name": "$CONTAINER_NAME",
    "files": [
        "sermon_data.tar.gz",
        "database.sql.gz",
        "config.tar.gz"
    ],
    "size": "$(du -sh $BACKUP_DIR/$DATE | cut -f1)"
}
EOF

# Cleanup old backups (keep last 7 days)
echo "🧹 Cleaning up old backups..."
find "$BACKUP_DIR" -type d -name "*_*" -mtime +7 -exec rm -rf {} \; 2>/dev/null || true

echo "✅ Backup completed: $BACKUP_DIR/$DATE"