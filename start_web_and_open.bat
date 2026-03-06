@echo off
cd /d "%~dp0"

echo ============================================================
echo Intercom Translation Workflow - Starting Web Server
echo ============================================================
echo.

set INTERCOM_ACCESS_TOKEN=your_intercom_access_token_here
set OPENAI_API_KEY=your_openai_api_key_here
set OPENAI_MODEL=gpt-4o-mini

echo Web page link: http://localhost:5000
echo.
echo Opening browser in 5 seconds...
echo Keep this window open while using the web page.
echo Press Ctrl+C to stop the server.
echo.

start "" cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:5000"

python run_web.py

pause
