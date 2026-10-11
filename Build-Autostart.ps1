param([string]$Python = (Join-Path $PSScriptRoot '.venv-devloop\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python scripts/build_autostart.py
    if ($LASTEXITCODE -ne 0) { throw 'Autostart build or artifact validation failed. No device changes were made.' }
} finally { Pop-Location }
