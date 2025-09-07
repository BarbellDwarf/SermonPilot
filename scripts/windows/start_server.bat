@echo off
echo Running real validation to generate cost tracking data...
call "d:\Repositories\sermon-ai-audio-processor\.venv\Scripts\activate.bat"
python "d:\Repositories\sermon-ai-audio-processor\tests\run_real_validation.py"
echo.
echo Starting Streamlit server...
echo The server will be available at http://localhost:8501
echo Press Ctrl+C to stop the server
streamlit run "d:\Repositories\sermon-ai-audio-processor\streamlit_app.py" --server.port 8501
pause
