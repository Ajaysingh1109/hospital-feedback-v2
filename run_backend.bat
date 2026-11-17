@echo off
echo Starting AI Hospital Patient Feedback Backend on http://localhost:8000...
cd /d "%~dp0backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
