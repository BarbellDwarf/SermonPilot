#!/bin/bash
# docker-start-dev.sh - Start development environment

set -e

echo "🛠️ Starting SermonAudio Processor Development Environment"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if Docker Compose is available
if ! docker compose version >/dev/null 2>&1; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Pull required base images
echo "📥 Pulling base images..."
docker pull redis:7-alpine
docker pull ollama/ollama:latest

# Start the development stack
echo "🚀 Starting development stack..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

echo "✅ Development environment started!"
echo "🌐 Access the application at: http://localhost:8501"