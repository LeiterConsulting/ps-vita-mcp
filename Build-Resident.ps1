$ErrorActionPreference = 'Stop'
$residentRoot = $PSScriptRoot
$residentPython = Join-Path $residentRoot '.venv-devloop\Scripts\python.exe'
$residentImage = (Get-Content -LiteralPath (Join-Path $residentRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
$residentEvidence = Join-Path $residentRoot ('evidence\resident\build-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $residentEvidence | Out-Null
Push-Location -LiteralPath $residentRoot
try {
    docker run --rm --network none --mount "type=bind,source=$residentRoot,target=/workspace" $residentImage sh -c 'sh resident/test_host.sh' 2>&1 | Tee-Object (Join-Path $residentEvidence 'c-service-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Resident C service tests failed.' }
    & $residentPython resident/test_bridge.py 2>&1 | Tee-Object (Join-Path $residentEvidence 'mcp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Resident MCP tests failed.' }
    & $residentPython resident/test_staging.py 2>&1 | Tee-Object (Join-Path $residentEvidence 'ftp-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Resident deployment tests failed.' }
    & $residentPython resident/test_update.py 2>&1 | Tee-Object (Join-Path $residentEvidence 'update-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Resident replacement tests failed.' }
    docker run --rm --network none --mount "type=bind,source=$residentRoot,target=/workspace" $residentImage sh -c 'cmake -S resident -B build/resident/native -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/resident/native && arm-vita-eabi-readelf -hlSW build/resident/native/vita_resident.velf > build/resident/native/elf-layout.txt && arm-vita-eabi-nm -u build/resident/native/vita_resident > build/resident/native/undefined-symbols.txt && arm-vita-eabi-size build/resident/native/vita_resident > build/resident/native/section-sizes.txt' 2>&1 | Tee-Object (Join-Path $residentEvidence 'native-build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Resident native build failed.' }
    & $residentPython resident/verify_build.py --evidence $residentEvidence
    if ($LASTEXITCODE -ne 0) { throw 'Resident native artifact validation failed.' }
    Write-Host 'Resident prototype built and host-checked. Device activation and multitasking proof are pending.'
} finally { Pop-Location }
