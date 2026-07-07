#!/bin/bash

# SermonPilot - Linux Server Startup Script
# This script starts the Streamlit server with proper environment setup

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get the directory where this script is run from, needs to be the root folder or the current working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}🚀 SermonPilot - Server Startup${NC}"
echo -e "${BLUE}=================================================${NC}"

# Check if virtual environment exists
if [ ! -d ".venv-linux" ] && [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found!${NC}"
    echo -e "${YELLOW}Please create a virtual environment first:${NC}"
    echo "  uv venv --python 3.11 .venv-linux"
    echo "  source .venv-linux/bin/activate"
    echo "  uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match"
    exit 1
fi

# Determine which virtual environment to use
if [ -d ".venv-linux" ]; then
    VENV_DIR=".venv-linux"
    echo -e "${GREEN}✅ Using Linux virtual environment: .venv-linux${NC}"
elif [ -d ".venv" ]; then
    VENV_DIR=".venv"
    echo -e "${GREEN}✅ Using virtual environment: .venv${NC}"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Check if required packages are installed
echo -e "${BLUE}🔍 Checking dependencies...${NC}"

if ! python -c "import streamlit" 2>/dev/null; then
    echo -e "${RED}❌ Streamlit not found!${NC}"
    echo -e "${YELLOW}Installing requirements...${NC}"
    if [ -f "requirements/requirements-linux.txt" ]; then
        uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
    else
        uv pip install -r requirements/requirements.txt
    fi
fi

# Verify key dependencies
echo -e "${BLUE}🧪 Verifying installation...${NC}"
python -c "
import sys
try:
    import torch
    print(f'✅ PyTorch {torch.__version__} (CUDA: {torch.cuda.is_available()})')
except ImportError:
    print('❌ PyTorch not found')
    sys.exit(1)

try:
    import streamlit
    print(f'✅ Streamlit {streamlit.__version__}')
except ImportError:
    print('❌ Streamlit not found')
    sys.exit(1)

try:
    import df
    print('✅ DeepFilterNet (df) available')
except ImportError:
    print('⚠️  DeepFilterNet not available (optional)')
"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Dependency check failed!${NC}"
    exit 1
fi

# Set environment variables
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Check if streamlit app exists
if [ ! -f "streamlit_app.py" ]; then
    echo -e "${RED}❌ streamlit_app.py not found!${NC}"
    exit 1
fi

# Start the server
echo -e "${GREEN}🌐 Starting Streamlit server...${NC}"
echo -e "${BLUE}📍 Server will be available at: http://localhost:8501${NC}"
echo -e "${YELLOW}📝 Press Ctrl+C to stop the server${NC}"
echo -e "${BLUE}=================================================${NC}"

# Function to handle cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Stopping server...${NC}"
    exit 0
}

# Set trap to handle Ctrl+C
trap cleanup SIGINT SIGTERM

# Start streamlit with optimal settings for Linux
streamlit run streamlit_app.py \
    --server.port 8501 \
    --server.address localhost \
    --browser.gatherUsageStats false \
    --server.headless true \
    --server.fileWatcherType none \
    --server.maxUploadSize 2000 \
    --theme.base light
