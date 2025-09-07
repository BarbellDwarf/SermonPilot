# Startup Scripts

This directory contains platform-specific startup scripts for the SermonAudio Processor.

## Linux Scripts (`linux/`)

### `start_server.sh`
Starts the main server application on Linux systems.

### `server.sh`  
Alternative server startup script with additional options.

**Usage:**
```bash
chmod +x scripts/linux/start_server.sh
./scripts/linux/start_server.sh
```

## Windows Scripts (`windows/`)

### `start_server.bat`
Starts the main server application on Windows systems.

### `start_streamlit.bat`
Starts the Streamlit web interface on Windows.

### `start_streamlit.ps1`
PowerShell script to start the Streamlit web interface.

**Usage:**
```cmd
# From Command Prompt
scripts\windows\start_server.bat

# From PowerShell
.\scripts\windows\start_streamlit.ps1
```

## Notes

- Make sure to set execute permissions on Linux scripts
- Scripts assume Python and dependencies are properly installed
- Check individual scripts for specific requirements and configuration needs