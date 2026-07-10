param(
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
& $Python (Join-Path $PSScriptRoot "init_secrets.py") --project-root $projectRoot
