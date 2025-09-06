@echo off
cd /d "d:\Repositories\sermon-ai-audio-processor"
echo Activating virtual environment...
call ".venv\Scripts\activate.bat"
echo Starting Streamlit server...
echo Server will be available at http://localhost:8501
echo.
streamlit run streamlit_app.py --server.port 8501 --server.address localhost --browser.gatherUsageStats false
