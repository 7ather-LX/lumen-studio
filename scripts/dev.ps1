# One-command development bootstrap for Windows.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating Python virtual environment..."
    # --without-pip avoids bootstrap issues on Python installs without ensurepip.
    python -m venv --without-pip .venv
    python -m pip install --target .venv\Lib\site-packages pip -r backend\requirements-dev.txt
}

Write-Host "Installing backend dependencies..."
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

if (-not (Test-Path "node_modules\electron\dist\electron.exe")) {
    Write-Host "Installing Node dependencies..."
    npm install
    node node_modules\electron\install.js
}

Write-Host "Starting Lumen Studio in development mode..."
npm run dev
