#!/bin/bash
# setup-docker.sh - Complete Docker environment setup

set -e

echo "🐳 SermonAudio Processor - Docker Environment Setup"
echo "================================================="

# Check prerequisites
echo "🔍 Checking prerequisites..."

# Check Docker
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
else
    echo "✅ Docker found: $(docker --version)"
fi

# Check Docker Compose
if ! docker compose version >/dev/null 2>&1; then
    echo "❌ Docker Compose is not available. Please install Docker Compose first."
    exit 1
else
    echo "✅ Docker Compose found: $(docker compose version)"
fi

# Check if running as root or in docker group
if ! docker ps >/dev/null 2>&1; then
    echo "❌ Cannot access Docker. Make sure Docker is running and your user is in the docker group."
    echo "   Run: sudo usermod -aG docker \$USER && newgrp docker"
    exit 1
else
    echo "✅ Docker access confirmed"
fi

# GPU support check (optional)
if docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
    echo "✅ NVIDIA GPU support available"
    GPU_SUPPORT=true
else
    echo "⚠️ NVIDIA GPU support not available (this is optional)"
    GPU_SUPPORT=false
fi

echo ""
echo "🛠️ Setting up environment..."

# Create .env.prod template if it doesn't exist
if [ ! -f .env.prod ]; then
    echo "📝 Creating .env.prod template..."
    cat > .env.prod << 'EOF'
# Production Environment Variables
# Update these values before running in production

POSTGRES_PASSWORD=your_secure_postgres_password_here
SERMONAUDIO_API_KEY=your_sermonaudio_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
XAI_API_KEY=your_xai_api_key_here

# Optional: Database configuration
DATABASE_URL=postgresql://sermon_user:${POSTGRES_PASSWORD}@postgres:5432/sermon_processor

# Optional: Ollama configuration
OLLAMA_HOST=http://ollama:11434
EOF
    echo "✅ Created .env.prod template"
else
    echo "✅ .env.prod already exists"
fi

# Create directories for volumes
echo "📁 Creating volume directories..."
mkdir -p data models logs config_backups backups
echo "✅ Volume directories created"

# Pull base images
echo "📥 Pulling required base images..."
docker pull redis:7-alpine
docker pull ollama/ollama:latest
if [ "$GPU_SUPPORT" = true ]; then
    docker pull nvidia/cuda:12.1-devel-ubuntu22.04
fi
echo "✅ Base images pulled"

echo ""
echo "🎯 Setup complete! Next steps:"
echo ""
echo "For Development:"
echo "  ./docker-start-dev.sh"
echo ""
echo "For Production:"
echo "  1. Edit .env.prod with your actual API keys and passwords"
echo "  2. ./docker-start-prod.sh"
echo ""
echo "Manual Commands:"
echo "  # Build images:     ./docker-build.sh"
echo "  # Start dev:        docker compose -f docker-compose.yml -f docker-compose.dev.yml up"
echo "  # Start prod:       docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo "  # View logs:        docker compose logs -f"
echo "  # Stop all:         docker compose down"
echo ""
echo "📖 See docker/README.md for detailed documentation"