@echo off
:: Change directory to the folder where this batch file is located
cd /d "%~dp0"

:: Check if virtual environment exists
if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERROR] Virtual environment not found. Please run setup first.
    pause
    exit /b
)

:: Start the agent in windowed mode (hides the cmd console window)
start "" ".venv\Scripts\pythonw.exe" local_agent.py
exit
