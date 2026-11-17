@echo off
echo Running Automated Backend & Acceptance Test Suite...
cd /d "%~dp0backend"
python -m pytest tests/ -v
