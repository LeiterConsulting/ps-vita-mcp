param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$vitaProjectRoot = $PSScriptRoot
$vitaPython = Join-Path $vitaProjectRoot '.venv-devloop\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $vitaPython)) { throw 'Run Setup-DevLoop.ps1 first to create the project Python environment.' }
$vitaImage = (Get-Content -LiteralPath (Join-Path $vitaProjectRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
New-Item -ItemType Directory -Path (Join-Path $vitaProjectRoot 'evidence\devloop') -Force | Out-Null
Push-Location -LiteralPath $vitaProjectRoot
try {
    & $vitaPython scripts/generate_devloop_assets.py
    if ($LASTEXITCODE -ne 0) { throw 'DevLoop artwork generation failed.' }
    if (-not $SkipTests) {
        docker run --rm --network none --mount "type=bind,source=$vitaProjectRoot,target=/workspace" $vitaImage sh scripts/test_devloop.sh 2>&1 | Tee-Object evidence/devloop/host-tests.log
        if ($LASTEXITCODE -ne 0) { throw 'Host physics/DevLoop tests failed.' }
        & $vitaPython scripts/check_publication_regression.py 2>&1 | Tee-Object evidence/devloop/publication-regression-check.log
        if ($LASTEXITCODE -ne 0) { throw 'Publication regression sensitivity check failed.' }
        & $vitaPython tests/test_bridge.py 2>&1 | Tee-Object evidence/devloop/bridge-tests.log
        if ($LASTEXITCODE -ne 0) { throw 'MCP bridge tests failed.' }
        & $vitaPython tests/test_scripts_bridge.py 2>&1 | Tee-Object evidence/devloop/script-bridge-tests.log
        if ($LASTEXITCODE -ne 0) { throw 'MCP Lua bridge tests failed.' }
        & $vitaPython tests/test_livearea.py 2>&1 | Tee-Object evidence/devloop/livearea-tests.log
        if ($LASTEXITCODE -ne 0) { throw 'LiveArea regression tests failed.' }
    }
    docker run --rm --network none --mount "type=bind,source=$vitaProjectRoot,target=/workspace" $vitaImage sh -c 'cmake -S . -B build/devloop -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/devloop --target vita_devloop.vpk' 2>&1 | Tee-Object evidence/devloop/vita-build.log
    if ($LASTEXITCODE -ne 0) { throw 'Native Vita DevLoop build failed.' }
    & $vitaPython scripts/verify_devloop_package.py
    if ($LASTEXITCODE -ne 0) { throw 'DevLoop package validation failed.' }
    if (-not $SkipTests) {
        & $vitaPython tests/test_ftp_staging.py 2>&1 | Tee-Object evidence/devloop/ftp-staging-tests.log
        if ($LASTEXITCODE -ne 0) { throw 'MCP FTP staging tests failed.' }
    }
    Write-Host 'DevLoop build verified. Device installation and live Wi-Fi proof remain separate.'
} finally { Pop-Location }
