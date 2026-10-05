$ErrorActionPreference = 'Stop'
$wbRoot = $PSScriptRoot
$wbPython = Join-Path $wbRoot '.venv-devloop\Scripts\python.exe'
$wbImage = (Get-Content -LiteralPath (Join-Path $wbRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
$wbEvidence = Join-Path $wbRoot ('evidence\workbench\build-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $wbEvidence -Force | Out-Null
Push-Location -LiteralPath $wbRoot
try {
    & $wbPython workbench/target/artwork.py
    if ($LASTEXITCODE -ne 0) { throw 'Target artwork failed.' }
    & $wbPython workbench/test_mcp.py 2>&1 | Tee-Object (Join-Path $wbEvidence 'mcp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Workbench MCP tests failed.' }
    & $wbPython workbench/test_power.py 2>&1 | Tee-Object (Join-Path $wbEvidence 'power-heartbeat-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Work power heartbeat tests failed.' }
    & $wbPython workbench/test_qualification.py 2>&1 | Tee-Object (Join-Path $wbEvidence 'input-qualification-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Input qualification decision tests failed.' }
    & $wbPython -m unittest workbench.test_physical workbench.test_disconnect workbench.test_journal 2>&1 | Tee-Object (Join-Path $wbEvidence 'physical-disconnect-journal-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Physical observation/disconnect/journal decision tests failed.' }
    & $wbPython tests/test_scripts_bridge.py 2>&1 | Tee-Object (Join-Path $wbEvidence 'foreground-mcp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Foreground MCP regression tests failed.' }
    docker run --rm --network none --mount "type=bind,source=$wbRoot,target=/workspace" $wbImage sh -c 'sh workbench/target/test_host.sh && cmake -S workbench/target -B build/workbench/target -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/workbench/target && arm-vita-eabi-nm -u build/workbench/target/input_target > build/workbench/target/undefined.txt' 2>&1 | Tee-Object (Join-Path $wbEvidence 'native-build-and-host-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Input Target build or host tests failed.' }
    & $wbPython workbench/target/verify_build.py $wbEvidence
    if ($LASTEXITCODE -ne 0) { throw 'Input Target verification failed.' }
    Write-Host "Workbench checked; device qualification remains pending. Evidence: $wbEvidence"
} finally { Pop-Location }
