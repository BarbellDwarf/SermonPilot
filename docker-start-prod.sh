#!/bin/bash
# docker-start-prod.sh - Start production environment

set -e

echo "🚀 Starting SermonAudio Processor Production Environment"

# Check for environment file
if [ ! -f .env.prod ]; then
    echo "⚠️ .env.prod not found. Creating template..."
    cat > .env.prod << EOF
# Production Environment Variables
POSTGRES_PASSWORD=your_secure_postgres_password
SERMONAUDIO_API_KEY=your_sermonaudio_api_key
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
XAI_API_KEY=your_xai_api_key
EOF
    echo "📝 Please edit .env.prod with your actual values before starting production"
    exit 1
fi

# Load production environment
export $(cat .env.prod | xargs)

# Start the production stack
echo "🚀 Starting production stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "✅ Production environment started!"
echo "🌐 Access the application at: http://localhost"
echo "📊 Monitor with: docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f"