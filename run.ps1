# PowerShell script to run Intercom Translation Workflow
Set-Location $PSScriptRoot

# Set environment variables
$env:INTERCOM_ACCESS_TOKEN = "your_intercom_access_token_here"
$env:OPENAI_API_KEY = "your_openai_api_key_here"
$env:OPENAI_MODEL = "gpt-4o-mini"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Intercom Translation Workflow" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check for Python
$pythonCmd = $null
$pythonPaths = @(
    "python",
    "python3",
    "py",
    "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
    "$env:ProgramFiles\Python*\python.exe",
    "C:\Python*\python.exe"
)

foreach ($path in $pythonPaths) {
    try {
        if (Test-Path $path) {
            $pythonCmd = $path
            break
        }
        $result = Get-Command $path -ErrorAction SilentlyContinue
        if ($result) {
            $pythonCmd = $path
            break
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.8 or higher from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing Python, run this script again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Found Python: $pythonCmd" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Host "Installing/updating dependencies..." -ForegroundColor Yellow
& $pythonCmd -m pip install -q requests openai python-dotenv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Test connections
Write-Host "Testing API connections..." -ForegroundColor Yellow
& $pythonCmd test_connection.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Connection test failed. Please check your API keys." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Running workflow in DRY-RUN mode..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
& $pythonCmd main.py --dry-run

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "To run actual translations, use:" -ForegroundColor Yellow
Write-Host "  python main.py" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Read-Host "Press Enter to exit"
