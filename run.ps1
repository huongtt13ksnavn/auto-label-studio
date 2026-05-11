<#
.SYNOPSIS
  Launch backend (FastAPI/uvicorn) and frontend (Vite) together.

.DESCRIPTION
  - Creates a Python venv in backend\.venv on first run and installs requirements.
  - Runs `npm install` in frontend\ on first run.
  - Streams both processes' output to this terminal.
  - Ctrl+C stops both cleanly.

.PARAMETER SkipInstall
  Skip dependency installation. Useful for fast restarts.

.PARAMETER BackendPort
  Override the backend port (default 8000).

.EXAMPLE
  .\run.ps1
  .\run.ps1 -SkipInstall
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [int]$BackendPort = 8000
)

$ErrorActionPreference = "Stop"
$root      = $PSScriptRoot
$backend   = Join-Path $root "backend"
$frontend  = Join-Path $root "frontend"
$venv      = Join-Path $backend ".venv"
$venvPy    = Join-Path $venv "Scripts\python.exe"
$venvPip   = Join-Path $venv "Scripts\pip.exe"

function Write-Section([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Require-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "$name not found on PATH. Install it and retry."
    }
}

Require-Command python
Require-Command npm

# ---- backend setup ----
if (-not (Test-Path $venv)) {
    Write-Section "Creating Python venv at backend\.venv"
    python -m venv $venv
}

if (-not $SkipInstall) {
    Write-Section "Installing backend deps (slow first time -- torch is ~750MB)"
    # Use `python -m pip` because pip cannot upgrade itself when invoked directly on Windows
    & $venvPy -m pip install --upgrade pip | Out-Null
    & $venvPy -m pip install -r (Join-Path $backend "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

# ---- frontend setup ----
if (-not (Test-Path (Join-Path $frontend "node_modules")) -and -not $SkipInstall) {
    Write-Section "Installing frontend deps"
    Push-Location $frontend
    try { npm install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
}

# ---- launch both ----
Write-Section "Starting backend on http://127.0.0.1:$BackendPort"
$backendProc = Start-Process `
    -FilePath $venvPy `
    -ArgumentList @("-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","$BackendPort","--reload") `
    -WorkingDirectory $root `
    -NoNewWindow `
    -PassThru

Write-Section "Starting frontend on http://localhost:5173"
# npm on Windows is npm.cmd; use cmd.exe to ensure shell resolution
$frontendProc = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList @("/c","npm","run","dev") `
    -WorkingDirectory $frontend `
    -NoNewWindow `
    -PassThru

Write-Host ""
Write-Host "Backend  PID $($backendProc.Id)  http://127.0.0.1:$BackendPort/docs" -ForegroundColor Green
Write-Host "Frontend PID $($frontendProc.Id)  http://localhost:5173" -ForegroundColor Green
Write-Host "Ctrl+C stops both." -ForegroundColor Yellow

function Stop-Tree([int]$processId) {
    if ($processId -le 0) { return }
    # taskkill /T kills the whole tree; uvicorn --reload and cmd->npm->node both
    # spawn descendants that Stop-Process alone won't reach.
    & taskkill.exe /F /T /PID $processId 2>&1 | Out-Null
}

function Stop-All {
    foreach ($p in @($backendProc, $frontendProc)) {
        if ($p -and -not $p.HasExited) {
            Stop-Tree $p.Id
        }
    }
    # belt-and-suspenders: kill anything still listening on our ports
    Get-NetTCPConnection -State Listen -LocalPort $BackendPort,5173 -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Tree $_.OwningProcess }
}

try {
    # poll both processes; exit when either dies
    while ($true) {
        Start-Sleep -Milliseconds 500
        if ($backendProc.HasExited) {
            Write-Host "Backend exited (code $($backendProc.ExitCode)). Shutting down frontend." -ForegroundColor Red
            break
        }
        if ($frontendProc.HasExited) {
            Write-Host "Frontend exited (code $($frontendProc.ExitCode)). Shutting down backend." -ForegroundColor Red
            break
        }
    }
} finally {
    Stop-All
    Write-Host "Stopped."
}
