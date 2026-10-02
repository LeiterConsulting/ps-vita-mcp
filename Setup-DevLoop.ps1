param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$environmentPython = Join-Path $projectRoot '.venv-devloop\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $environmentPython)) {
    & $Python -m venv (Join-Path $projectRoot '.venv-devloop')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment. Use -Python with your Python 3.13 executable path.' }
}
& $environmentPython -m pip install -r (Join-Path $projectRoot 'bridge\requirements-lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing pinned bridge dependencies failed.' }
Write-Host 'Project Python environment ready. Start Docker Desktop, then run Build-DevLoop.ps1.'
