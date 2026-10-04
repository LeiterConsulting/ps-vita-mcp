param([switch]$IncludeInspector)
$ErrorActionPreference = 'Stop'
# These builds use only host adapters/local fixtures; they never contact a Vita.
& (Join-Path $PSScriptRoot 'Build-DevLoop.ps1')
& (Join-Path $PSScriptRoot 'Build-Resident.ps1')
& (Join-Path $PSScriptRoot 'Build-Control.ps1')
& (Join-Path $PSScriptRoot 'Build-Workbench.ps1')
if ($IncludeInspector) { & (Join-Path $PSScriptRoot 'Build-Inspector.ps1') }
Write-Host 'Baseline components built and host checked. Follow docs/GETTING-STARTED.md for manual device setup and acceptance.'
