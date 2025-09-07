#!/usr/bin/env python3
"""
Start the Streamlit server using subprocess
"""
import subprocess
import sys
import os
import time
from pathlib import Path

def start_streamlit_server():
    """Start streamlit server in background"""
    project_root = Path(__file__).parent
    streamlit_app = project_root / "streamlit_app.py"
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    
    print("Starting Streamlit server...")
    print(f"Using Python: {venv_python}")
    print(f"App file: {streamlit_app}")
    print("Server will be available at: http://localhost:8501")
    print("-" * 50)
    
    # Set environment variables
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    
    # Command to run streamlit
    cmd = [
        str(venv_python),
        "-m", "streamlit",
        "run", str(streamlit_app),
        "--server.port", "8501",
        "--server.address", "localhost",
        "--browser.gatherUsageStats", "false",
        "--server.headless", "true"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        # Start the process
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        print(f"Streamlit server started with PID: {process.pid}")
        print("Waiting for server to start...")
        
        # Give it a moment to start
        time.sleep(3)
        
        # Check if process is still running
        if process.poll() is None:
            print("✅ Server appears to be running!")
            print("🌐 Access the app at: http://localhost:8501")
            return process
        else:
            print("❌ Server failed to start")
            stdout, stderr = process.communicate()
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return None
            
    except Exception as e:
        print(f"Error starting server: {e}")
        return None

if __name__ == "__main__":
    process = start_streamlit_server()
    if process:
        try:
            # Keep the script running
            print("Press Ctrl+C to stop the server...")
            process.wait()
        except KeyboardInterrupt:
            print("\nStopping server...")
            process.terminate()
            process.wait()
            print("Server stopped.")
