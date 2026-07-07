@echo off
echo Running real validation to generate cost tracking data...
call "d:\Repositories\SermonPilot\.venv\Scripts\activate.bat"
python "d:\Repositories\SermonPilot\tests\run_real_validation.py"
echo.
echo Starting Streamlit server...
echo The server will be available at http://localhost:8501
echo Press Ctrl+C to stop the server
streamlit run "d:\Repositories\SermonPilot\streamlit_app.py" --server.port 8501
pause
