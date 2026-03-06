@echo off
REM Batch file to run the Intercom Translation Workflow
cd /d "%~dp0"

REM Set environment variables
set INTERCOM_ACCESS_TOKEN=your_intercom_access_token_here
set OPENAI_API_KEY=your_openai_api_key_here
set OPENAI_MODEL=gpt-4o-mini

echo ========================================
echo Intercom Translation Workflow
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

echo Installing/updating dependencies...
python -m pip install -q requests openai python-dotenv

echo.
echo Testing API connections...
python test_connection.py

if errorlevel 1 (
    echo.
    echo Connection test failed. Please check your API keys.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Running workflow in DRY-RUN mode...
echo ========================================
python main.py --dry-run

echo.
echo ========================================
echo To run actual translations, use:
echo   python main.py
echo ========================================
pause
