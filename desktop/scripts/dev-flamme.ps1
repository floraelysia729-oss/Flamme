param(
    [string]$VaultPath = "",
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$desktopRoot = Split-Path -Parent $PSScriptRoot
$monorepoRoot = Split-Path -Parent $desktopRoot
$backendRoot = Join-Path $desktopRoot "flamme-backend"

if (-not (Test-Path (Join-Path $backendRoot "src\api\app.py"))) {
    if (Test-Path (Join-Path $monorepoRoot "src\api\app.py")) {
        $backendRoot = $monorepoRoot
    } else {
        Write-Error "Flamme backend not found at: $backendRoot or monorepo root $monorepoRoot"
    }
}

function Resolve-FlammePython {
    param([string]$BackendRoot)

    if ($env:FLAMME_PYTHON -and (Test-Path $env:FLAMME_PYTHON)) {
        return (Resolve-Path $env:FLAMME_PYTHON).Path
    }

    $pathFile = Join-Path $BackendRoot ".python-path"
    if (Test-Path $pathFile) {
        $fromFile = (Get-Content $pathFile -TotalCount 1).Trim()
        if ($fromFile -and (Test-Path $fromFile)) {
            return (Resolve-Path $fromFile).Path
        }
    }

    foreach ($candidate in @(
        (Join-Path $BackendRoot ".venv\Scripts\python.exe"),
        (Join-Path $BackendRoot "venv\Scripts\python.exe")
    )) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    Write-Error "Python not found. Set FLAMME_PYTHON, create flamme-backend/.python-path, or install a venv under flamme-backend."
}

$pythonExe = Resolve-FlammePython -BackendRoot $backendRoot

if (-not $VaultPath) {
    $demoVault = Join-Path $repoRoot "demo-vault-v2"
    if (Test-Path $demoVault) {
        $VaultPath = (Resolve-Path $demoVault).Path
    } else {
        Write-Error "Set -VaultPath to your active vault directory."
    }
}

$env:FLAMME_VAULT_PATH = (Resolve-Path $VaultPath).Path
$env:FLAMME_WIKI_DIR = Join-Path $env:FLAMME_VAULT_PATH ".wiki"
$env:FLAMME_DESKTOP = "1"

$portInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    $ownerPid = $portInUse[0].OwningProcess
    $owner = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
    $ownerName = if ($owner) { $owner.ProcessName } else { "pid=$ownerPid" }
    Write-Host "Port $Port is already in use by $ownerName (PID $ownerPid)." -ForegroundColor Yellow
    Write-Host "Stop it with: Stop-Process -Id $ownerPid -Force"
    Write-Host "Or use another port: .\scripts\dev-flamme.ps1 -VaultPath `"$VaultPath`" -Port 8766"
    exit 1
}

Write-Host "FLAMME_VAULT_PATH=$($env:FLAMME_VAULT_PATH)"
Write-Host "Using Python: $pythonExe"
Write-Host "Starting uvicorn on 127.0.0.1:$Port ..."

Set-Location $backendRoot
& $pythonExe -m uvicorn src.api.app:app --host 127.0.0.1 --port $Port
