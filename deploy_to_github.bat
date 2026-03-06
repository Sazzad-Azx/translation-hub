@echo off
echo === Preparing for GitHub Deployment ===
echo.

REM Check if Git is available
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Git is not installed or not in PATH
    echo.
    echo Please install Git from: https://git-scm.com/download/win
    echo Or run: winget install Git.Git
    echo.
    pause
    exit /b 1
)

echo Git is installed!
git --version
echo.

REM Change to script directory
cd /d "%~dp0"

REM Initialize Git if needed
if not exist ".git" (
    echo Initializing Git repository...
    git init
    echo.
)

REM Check .env file
if exist ".env" (
    echo WARNING: .env file exists - make sure it's in .gitignore
    findstr /C:".env" .gitignore >nul
    if %ERRORLEVEL% EQU 0 (
        echo .env is in .gitignore - OK
    ) else (
        echo ERROR: .env is NOT in .gitignore!
        pause
        exit /b 1
    )
    echo.
)

echo Current Git status:
git status --short
echo.

echo === Ready for deployment ===
echo.
echo Next steps:
echo 1. git add .
echo 2. git commit -m "Initial commit: Ready for Vercel"
echo 3. Create repo on GitHub.com
echo 4. git remote add origin https://github.com/USERNAME/REPO.git
echo 5. git push -u origin main
echo.
pause
