#!/bin/bash

# SermonPilot - Advanced Linux Server Manager
# This script provides start/stop/status/restart functionality

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$SCRIPT_DIR/.streamlit.pid"
LOGFILE="$SCRIPT_DIR/server.log"
PORT=8501

cd "$SCRIPT_DIR"

# Function to show usage
show_usage() {
    echo -e "${BLUE}SermonPilot - Server Manager${NC}"
    echo ""
    echo "Usage: $0 {start|stop|restart|status|logs}"
    echo ""
    echo "Commands:"
    echo -e "  ${GREEN}start${NC}   - Start the Streamlit server"
    echo -e "  ${RED}stop${NC}    - Stop the Streamlit server"
    echo -e "  ${YELLOW}restart${NC} - Restart the Streamlit server"
    echo -e "  ${CYAN}status${NC}  - Show server status"
    echo -e "  ${BLUE}logs${NC}    - Show server logs"
    echo ""
}

# Function to check if server is running
is_running() {
    if [ -f "$PIDFILE" ]; then
        local pid=$(cat "$PIDFILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            return 0
        else
            rm -f "$PIDFILE"
            return 1
        fi
    fi
    return 1
}

# Function to get server status
get_status() {
    if is_running; then
        local pid=$(cat "$PIDFILE")
        echo -e "${GREEN}✅ Server is running${NC} (PID: $pid)"
        echo -e "${BLUE}🌐 URL: http://localhost:$PORT${NC}"
        if command -v ss >/dev/null 2>&1; then
            if ss -tuln | grep -q ":$PORT "; then
                echo -e "${GREEN}🔌 Port $PORT is active${NC}"
            else
                echo -e "${YELLOW}⚠️  Port $PORT not detected (server may be starting)${NC}"
            fi
        fi
    else
        echo -e "${RED}❌ Server is not running${NC}"
    fi
}

# Function to start the server
start_server() {
    echo -e "${BLUE}🚀 Starting SermonPilot Server${NC}"
    echo -e "${BLUE}================================================${NC}"

    if is_running; then
        echo -e "${YELLOW}⚠️  Server is already running!${NC}"
        get_status
        return 0
    fi

    # Check virtual environment
    if [ ! -d ".venv-linux" ] && [ ! -d ".venv" ]; then
        echo -e "${RED}❌ Virtual environment not found!${NC}"
        echo -e "${YELLOW}Please run setup first:${NC}"
        echo "  uv venv --python 3.11 .venv-linux"
        echo "  source .venv-linux/bin/activate"
        echo "  uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match"
        exit 1
    fi

    # Determine virtual environment
    if [ -d ".venv-linux" ]; then
        VENV_DIR=".venv-linux"
    else
        VENV_DIR=".venv"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"

    # Quick dependency check
    if ! python -c "import streamlit, torch" 2>/dev/null; then
        echo -e "${RED}❌ Required dependencies not found!${NC}"
        echo -e "${YELLOW}Installing requirements...${NC}"
        if [ -f "requirements/requirements-linux.txt" ]; then
            uv pip install -r requirements/requirements-linux.txt --index-strategy unsafe-best-match
        else
            uv pip install -r requirements/requirements.txt
        fi
    fi

    # Check streamlit app
    if [ ! -f "streamlit_app.py" ]; then
        echo -e "${RED}❌ streamlit_app.py not found!${NC}"
        exit 1
    fi

    # Set environment
    export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

    echo -e "${GREEN}🌐 Starting server on http://localhost:$PORT${NC}"

    # Start streamlit in background
    nohup streamlit run streamlit_app.py \
        --server.port $PORT \
        --server.address localhost \
        --browser.gatherUsageStats false \
        --server.headless true \
        --server.fileWatcherType none \
        --server.maxUploadSize 2000 \
        --theme.base light \
        > "$LOGFILE" 2>&1 &

    local pid=$!
    echo $pid > "$PIDFILE"

    # Wait a bit and check if it started successfully
    sleep 3
    if is_running; then
        echo -e "${GREEN}✅ Server started successfully!${NC}"
        get_status
    else
        echo -e "${RED}❌ Failed to start server${NC}"
        echo -e "${YELLOW}Check logs with: $0 logs${NC}"
        exit 1
    fi
}

# Function to stop the server
stop_server() {
    echo -e "${YELLOW}🛑 Stopping server...${NC}"
    
    if ! is_running; then
        echo -e "${YELLOW}⚠️  Server is not running${NC}"
        return 0
    fi

    local pid=$(cat "$PIDFILE")
    kill "$pid" 2>/dev/null || true
    
    # Wait for graceful shutdown
    local count=0
    while [ $count -lt 10 ] && ps -p "$pid" > /dev/null 2>&1; do
        sleep 1
        ((count++))
    done
    
    # Force kill if still running
    if ps -p "$pid" > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Forcing shutdown...${NC}"
        kill -9 "$pid" 2>/dev/null || true
    fi
    
    rm -f "$PIDFILE"
    echo -e "${GREEN}✅ Server stopped${NC}"
}

# Function to restart the server
restart_server() {
    echo -e "${BLUE}🔄 Restarting server...${NC}"
    stop_server
    sleep 2
    start_server
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}📋 Server Logs${NC}"
    echo -e "${BLUE}=============${NC}"
    
    if [ -f "$LOGFILE" ]; then
        tail -50 "$LOGFILE"
    else
        echo -e "${YELLOW}⚠️  No log file found${NC}"
    fi
}

# Main script logic
case "$1" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        get_status
        ;;
    logs)
        show_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
