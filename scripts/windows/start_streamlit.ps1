# PowerShell script to start Streamlit server
Set-Location "d:\Repositories\SermonPilot"
Write-Host "Activating virtual environment..." -ForegroundColor Green
& ".\.venv\Scripts\Activate.ps1"
Write-Host "Starting Streamlit server..." -ForegroundColor Green
Write-Host "Server will be available at http://localhost:8501" -ForegroundColor Yellow
Write-Host ""
& ".\.venv\Scripts\streamlit.exe" run streamlit_app.py --server.port 8501 --server.address localhost --browser.gatherUsageStats false
