param([ValidatePattern('^[A-Z]$')][string]$DriveLetter = 'F', [switch]$AllowUpdate)
$ErrorActionPreference = 'Stop'
$vitaProjectRoot = $PSScriptRoot
$vitaDist = Join-Path $vitaProjectRoot 'dist\devloop'
$vitaReport = Get-Content -LiteralPath (Join-Path $vitaDist 'build-report.json') -Raw | ConvertFrom-Json
$vitaVolume = Get-Volume -DriveLetter $DriveLetter -ErrorAction Stop
$vitaPartition = Get-Partition -DriveLetter $DriveLetter -ErrorAction Stop
$vitaDisk = Get-Disk -Number $vitaPartition.DiskNumber -ErrorAction Stop
if ($vitaDisk.BusType -ne 'USB' -or $vitaDisk.FriendlyName -notmatch 'PS Vita') { throw 'Drive is not the Sony Vita USB storage.' }
$vitaDriveRoot = $DriveLetter + ':\'
if (-not (Test-Path -LiteralPath (Join-Path $vitaDriveRoot 'app')) -or -not (Test-Path -LiteralPath (Join-Path $vitaDriveRoot 'data'))) { throw 'Vita storage layout missing.' }
if ($vitaVolume.SizeRemaining -lt ($vitaReport.package.bytes + 20MB)) { throw 'Insufficient free space.' }
$vitaAlreadyInstalled = Test-Path -LiteralPath (Join-Path $vitaDriveRoot 'app\CHRS00003')
if ($vitaAlreadyInstalled -and -not $AllowUpdate) { throw 'CHRS00003 already installed. Use -AllowUpdate for an authorized DevLoop repair.' }
$vitaLocalPackage = Join-Path $vitaDist 'vita_devloop.vpk'
if ((Get-FileHash -LiteralPath $vitaLocalPackage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $vitaReport.package.sha256) { throw 'Local VPK differs from its build report.' }
& (Join-Path $vitaProjectRoot '.venv-devloop\Scripts\python.exe') (Join-Path $vitaProjectRoot 'bridge\configure.py')
if ($LASTEXITCODE -ne 0) { throw 'Pairing configuration failed.' }
$vitaPrivateCfg = Join-Path $vitaProjectRoot '.devloop-private\bridge.cfg'
$vitaPairDirectory = Join-Path $vitaDriveRoot 'data\vita-devloop'
New-Item -ItemType Directory -Path $vitaPairDirectory -Force | Out-Null
$vitaPairDestination = Join-Path $vitaPairDirectory 'bridge.cfg'
if (Test-Path -LiteralPath $vitaPairDestination) {
    if ((Get-FileHash -LiteralPath $vitaPairDestination).Hash -ne (Get-FileHash -LiteralPath $vitaPrivateCfg).Hash) { throw 'Device pairing config already exists with a different token; preserve it for review.' }
} else { Copy-Item -LiteralPath $vitaPrivateCfg -Destination $vitaPairDestination }
$vitaStageName = Get-Date -Format 'yyyy-MM-dd_HHmmss-fff'
$vitaStageDirectory = Join-Path $vitaDriveRoot "data\codex-vita-devloop\$vitaStageName"
New-Item -ItemType Directory -Path $vitaStageDirectory | Out-Null
foreach ($vitaFileName in @('vita_devloop.vpk','SHA256SUMS.txt','build-report.json')) {
    $vitaFrom = Join-Path $vitaDist $vitaFileName
    $vitaTo = Join-Path $vitaStageDirectory $vitaFileName
    Copy-Item -LiteralPath $vitaFrom -Destination $vitaTo
    $vitaStream = [System.IO.File]::Open($vitaTo,[System.IO.FileMode]::Open,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::Read)
    try { $vitaStream.Flush($true) } finally { $vitaStream.Dispose() }
    if ((Get-FileHash -LiteralPath $vitaFrom).Hash -ne (Get-FileHash -LiteralPath $vitaTo).Hash) { throw "Device hash mismatch: $vitaFileName" }
}
$vitaCfgStream = [System.IO.File]::Open($vitaPairDestination,[System.IO.FileMode]::Open,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::Read)
try { $vitaCfgStream.Flush($true) } finally { $vitaCfgStream.Dispose() }
if ((Get-FileHash -LiteralPath $vitaPairDestination).Hash -ne (Get-FileHash -LiteralPath $vitaPrivateCfg).Hash) { throw 'Device pairing copy differs.' }
[ordered]@{ stagedUtc = [DateTimeOffset]::UtcNow.ToString('o'); disk = $vitaDisk.FriendlyName; serial = $vitaDisk.SerialNumber.Trim(); path = "ux0:data/codex-vita-devloop/$vitaStageName/vita_devloop.vpk"; version = $vitaReport.package.version; packageSha256 = $vitaReport.package.sha256; pairingVerified = $true; update = [bool]$vitaAlreadyInstalled; installation = 'pending'; physicalWifiAcceptance = 'pending' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $vitaProjectRoot 'evidence\devloop\device-staging.json') -Encoding utf8
Write-Host "Copied and SHA-256 verified: ux0:data/codex-vita-devloop/$vitaStageName/vita_devloop.vpk"
Write-Host 'Pairing configuration copied and verified. Install the VPK, open Vita DevLoop and read its Wi-Fi IP.'
