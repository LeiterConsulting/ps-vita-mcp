$ErrorActionPreference = 'Stop'
$residentRoot = Split-Path -Parent $PSScriptRoot
$residentPython = Join-Path $residentRoot '.venv-devloop\Scripts\python.exe'
$residentBridge = Join-Path $PSScriptRoot 'bridge.py'
$residentCodex = (Get-Command codex -ErrorAction Stop).Source
$residentCurrent = & $residentCodex mcp get vita_resident --json 2>$null
if ($LASTEXITCODE -eq 0) {
    $residentEntry = $residentCurrent | ConvertFrom-Json
    if ($residentEntry.transport.type -ne 'stdio' -or $residentEntry.transport.command -ne $residentPython -or @($residentEntry.transport.args).Count -ne 1 -or $residentEntry.transport.args[0] -ne $residentBridge) { throw 'An existing vita_resident entry points elsewhere; registration refused.' }
    Write-Host 'vita_resident already points to this bridge.'
    exit 0
}
$residentConfigBase = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$residentConfigFile = Join-Path $residentConfigBase 'config.toml'
$residentBackupDir = Join-Path $residentRoot '.devloop-private'
New-Item -ItemType Directory -Path $residentBackupDir -Force | Out-Null
if (Test-Path -LiteralPath $residentConfigFile) {
    $residentBackup = Join-Path $residentBackupDir ('codex-config-before-resident-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '.toml')
    Copy-Item -LiteralPath $residentConfigFile -Destination $residentBackup
}
& $residentCodex mcp add vita_resident -- $residentPython $residentBridge
if ($LASTEXITCODE -ne 0) { throw 'Resident MCP registration failed.' }
$residentRegistered = & $residentCodex mcp get vita_resident --json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $residentRegistered.transport.command -ne $residentPython -or $residentRegistered.transport.args[0] -ne $residentBridge) { throw 'Resident MCP registration read-back failed.' }
Write-Host 'vita_resident registered. Refresh the local MCP connection to discover four Resident and thirteen Control tools.'
