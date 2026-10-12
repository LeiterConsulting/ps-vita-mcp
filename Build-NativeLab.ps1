param(
    [ValidatePattern('^[0-9]{2}\.[0-9]{2}$')][string]$Version = '01.00',
    [ValidateSet(1, 2)][int]$Variant = 1
)
$ErrorActionPreference = 'Stop'
$labRoot = $PSScriptRoot
$labPython = Join-Path $labRoot '.venv-devloop\Scripts\python.exe'
$labImage = (Get-Content -LiteralPath (Join-Path $labRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
$labEvidence = Join-Path $labRoot ('evidence\native-lab\build-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
$labBuild = "build/native-lab-$Version-$Variant"
function Invoke-LabChecked([scriptblock]$Command, [string]$Log, [string]$Failure) {
    # Windows PowerShell 5 treats native stderr as ErrorRecords; unittest uses
    # stderr for successful progress. The process exit code decides success.
    $ErrorActionPreference = 'Continue'
    & $Command 2>&1 | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $Log
    if ($LASTEXITCODE -ne 0) { throw $Failure }
}
New-Item -ItemType Directory -Path $labEvidence | Out-Null
Push-Location -LiteralPath $labRoot
try {
    Invoke-LabChecked { docker run --rm --network none --mount "type=bind,source=$labRoot,target=/workspace" --workdir /workspace $labImage sh lifecycle_lab/test_host.sh } (Join-Path $labEvidence 'host-core-http-tests.log') 'Native lab host core and HTTP tests failed.'
    # Version and Variant are validated scalar arguments, never arbitrary shell text.
    $labCommand = "cmake -S lifecycle_lab -B $labBuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DLAB_VERSION=$Version -DLAB_VARIANT=$Variant && cmake --build $labBuild --target native_lab.vpk && arm-vita-eabi-readelf -hlSW $labBuild/native_lab.velf > $labBuild/elf-layout.txt && arm-vita-eabi-nm -u $labBuild/native_lab > $labBuild/undefined-symbols.txt && arm-vita-eabi-size $labBuild/native_lab > $labBuild/section-sizes.txt"
    Invoke-LabChecked { docker run --rm --network none --mount "type=bind,source=$labRoot,target=/workspace" --workdir /workspace $labImage sh -c $labCommand } (Join-Path $labEvidence 'native-build.log') 'Native lab ARM build failed.'
    Invoke-LabChecked { & $labPython lifecycle_lab/verify_build.py --build $labBuild --version $Version --variant $Variant --evidence $labEvidence } (Join-Path $labEvidence 'package-validation.log') 'Native lab package validation failed.'
    Write-Host "Native lab $Version variant $Variant built and host-checked. Device installation and lifecycle qualification remain pending. Evidence: $labEvidence"
} finally { Pop-Location }
