$ErrorActionPreference = 'Stop'
$controlRoot = $PSScriptRoot
$controlPython = Join-Path $controlRoot '.venv-devloop\Scripts\python.exe'
$controlImage = (Get-Content -LiteralPath (Join-Path $controlRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
$controlEvidence = Join-Path $controlRoot ('evidence\control\build-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $controlEvidence -Force | Out-Null
Push-Location -LiteralPath $controlRoot
try {
    & $controlPython resident/control/starter_artwork.py
    if ($LASTEXITCODE -ne 0) { throw 'Starter artwork failed.' }
    docker run --rm --network none --mount "type=bind,source=$controlRoot,target=/workspace" $controlImage sh -c 'sh resident/control/test_host.sh' 2>&1 | Tee-Object (Join-Path $controlEvidence 'host-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Control C tests failed.' }
    & $controlPython resident/control/test_bridge.py 2>&1 | Tee-Object (Join-Path $controlEvidence 'mcp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Control MCP tests failed.' }
    & $controlPython resident/test_bridge.py 2>&1 | Tee-Object (Join-Path $controlEvidence 'resident-mcp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Existing resident MCP regression tests failed.' }
    & $controlPython resident/control/test_staging.py 2>&1 | Tee-Object (Join-Path $controlEvidence 'staging-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Control staging tests failed.' }
    docker run --rm --network none --mount "type=bind,source=$controlRoot,target=/workspace" $controlImage sh -c 'cmake -S resident/control -B build/resident/control -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/resident/control && for mod in vita_control vita_control_kernel control_bootstrap_probe control_starter; do arm-vita-eabi-nm -u build/resident/control/$mod > build/resident/control/$mod-undefined.txt; arm-vita-eabi-readelf -hlSW build/resident/control/$mod.velf > build/resident/control/$mod-layout.txt; done' 2>&1 | Tee-Object (Join-Path $controlEvidence 'native-build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Control ARM build failed.' }
    & $controlPython resident/control/verify_build.py --evidence $controlEvidence
    if ($LASTEXITCODE -ne 0) { throw 'Control artifact verification failed.' }
    & $controlPython resident/control/test_starter_staging.py 2>&1 | Tee-Object (Join-Path $controlEvidence 'starter-staging-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Runtime starter staging safeguards failed.' }
    & $controlPython resident/control/test_retire_session.py 2>&1 | Tee-Object (Join-Path $controlEvidence 'session-retirement-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Starter session retirement safeguards failed.' }
    Write-Host 'Matched control pair built and host checked; device activation and physical acceptance remain pending.'
} finally { Pop-Location }
