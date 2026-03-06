# Git Setup and Deployment Script
Write-Host "=== Git Setup and Deployment Preparation ===" -ForegroundColor Cyan
Write-Host ""

# Check if Git is installed
$gitCheck = Get-Command git -ErrorAction SilentlyContinue
if ($gitCheck) {
    $gitVersion = git --version
    Write-Host "✓ Git is installed: $gitVersion" -ForegroundColor Green
    $gitInstalled = $true
} else {
    Write-Host "✗ Git is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Git from: https://git-scm.com/download/win" -ForegroundColor Yellow
    Write-Host "Or install via winget: winget install Git.Git" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "After installing Git, please restart this script." -ForegroundColor Yellow
    exit 1
}

# Change to project directory
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir
Write-Host "Project directory: $projectDir" -ForegroundColor Cyan
Write-Host ""

# Check if already a git repository
if (Test-Path ".git") {
    Write-Host "✓ Git repository already initialized" -ForegroundColor Green
    git status
} else {
    Write-Host "Initializing Git repository..." -ForegroundColor Yellow
    git init
    Write-Host "✓ Git repository initialized" -ForegroundColor Green
}

# Check for .env file and warn if it exists
if (Test-Path ".env") {
    Write-Host ""
    Write-Host "⚠ WARNING: .env file found!" -ForegroundColor Red
    Write-Host "Make sure .env is in .gitignore (it should be)" -ForegroundColor Yellow
    $envInGitignore = Select-String -Path ".gitignore" -Pattern "\.env" -Quiet
    if ($envInGitignore) {
        Write-Host "✓ .env is in .gitignore - safe to commit" -ForegroundColor Green
    } else {
        Write-Host "✗ .env is NOT in .gitignore - DO NOT COMMIT!" -ForegroundColor Red
        exit 1
    }
}

# Show what will be committed
Write-Host ""
Write-Host "Files ready to commit:" -ForegroundColor Cyan
git status --short

Write-Host ""
Write-Host "=== Next Steps ===" -ForegroundColor Cyan
Write-Host "1. Review the files above"
Write-Host "2. Run: git add ."
Write-Host "3. Run: git commit -m 'Initial commit: Ready for Vercel deployment'"
Write-Host "4. Create repository on GitHub.com"
Write-Host "5. Run: git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git"
Write-Host "6. Run: git push -u origin main"
Write-Host ""
