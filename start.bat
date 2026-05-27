@echo off
REM Quick start for Windows
echo ================================================================
echo   Onboarding Assignment Agent (A2A) — Setup
echo ================================================================

REM Create venv
if not exist ".venv" (
    echo Creating Python 3.12 virtual environment...
    py -3.12 -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt -q

echo.
echo ================================================================
echo   Starting agent on http://localhost:5000
echo   Agent Card: http://localhost:5000/agent-card
echo ================================================================
echo.

python -m app.main --port 5000
