#!/bin/bash
# docker-build.sh - Build all Docker images

set -e

echo "🐳 Building Docker images for SermonAudio Processor"

# Build base application image
echo "📦 Building base application image..."
docker build -t sermon-processor:latest .

# Build development image
echo "🛠️ Building development image..."
docker build -f Dockerfile.dev -t sermon-processor:dev .

# Build production image  
echo "🚀 Building production image..."
docker build -f Dockerfile.prod -t sermon-processor:prod .

echo "✅ All images built successfully!"
echo ""
echo "Available images:"
docker images | grep sermon-processor