param([ValidateSet("build", "serve", "smoke")][string]$Command = "serve")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Create .venv and install services/api/requirements-dev.txt first."
}
& $python (Join-Path $PSScriptRoot "local_staging.py") $Command
if ($LASTEXITCODE -ne 0) { throw "Local staging command failed." }
