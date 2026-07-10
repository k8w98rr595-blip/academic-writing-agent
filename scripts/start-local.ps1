$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$bundledRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies"
$bundledPnpm = Join-Path $bundledRoot "bin\fallback\pnpm.cmd"
$bundledNodeBin = Join-Path $bundledRoot "node\bin"
$pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
$pnpm = if ($pnpmCommand) { $pnpmCommand.Source } elseif (Test-Path $bundledPnpm) { $bundledPnpm } else { $null }
$nodeBin = if ($nodeCommand) { Split-Path -Parent $nodeCommand.Source } elseif (Test-Path (Join-Path $bundledNodeBin "node.exe")) { $bundledNodeBin } else { $null }

if (-not (Test-Path $python)) {
    throw "Python environment not found. Create .venv and install services/api/requirements-dev.txt first."
}
if (-not $pnpm -or -not $nodeBin) {
    throw "Node.js and pnpm were not found on PATH or in the Codex bundled runtime."
}
if (-not (Test-Path (Join-Path $root ".env.local"))) {
    & $python (Join-Path $root "scripts\init_secrets.py") --project-root $root
}

$env:Path = "$nodeBin;$(Split-Path -Parent $pnpm);$env:Path"
$api = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "services.api.app.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $root -WindowStyle Hidden -PassThru
$web = Start-Process -FilePath $pnpm -ArgumentList "--filter", "@paperlight/web", "dev" -WorkingDirectory $root -WindowStyle Hidden -PassThru

Write-Host "Paperlight is starting at http://127.0.0.1:3000"
Write-Host "API health: http://127.0.0.1:8000/api/health"
Write-Host "Process IDs: web=$($web.Id), api=$($api.Id)"
Write-Host "Use Stop-Process -Id $($web.Id),$($api.Id) when finished."
