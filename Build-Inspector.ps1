$ErrorActionPreference = 'Stop'
$inspectorRoot = $PSScriptRoot
$inspectorPython = Join-Path $inspectorRoot '.venv-devloop\Scripts\python.exe'
$inspectorImage = (Get-Content -LiteralPath (Join-Path $inspectorRoot 'toolchain.lock.json') -Raw | ConvertFrom-Json).image
$inspectorEvidence = Join-Path $inspectorRoot ('evidence\control\inspector-build-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
New-Item -ItemType Directory -Path $inspectorEvidence -Force | Out-Null
Push-Location -LiteralPath $inspectorRoot
try {
    & $inspectorPython resident/inspector/prepare.py
    if ($LASTEXITCODE -ne 0) { throw 'Inspector artwork failed.' }
    docker run --rm --network none --mount "type=bind,source=$inspectorRoot,target=/workspace" $inspectorImage sh -c 'mkdir -p build/resident/inspector && cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -DVI_HOST -DVI_BUILD_ID=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\" resident/inspector/kernel.c resident/inspector/test_kernel.c -o build/resident/inspector/kernel-tests && build/resident/inspector/kernel-tests' 2>&1 | Tee-Object (Join-Path $inspectorEvidence 'kernel-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Inspector metadata tests failed.' }
    docker run --rm --network none --mount "type=bind,source=$inspectorRoot,target=/workspace" $inspectorImage sh -c 'cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -DVI_HOST -DVI_BUILD_ID=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\" resident/inspector/proxy.c resident/inspector/test_proxy.c -o build/resident/inspector/proxy-tests && build/resident/inspector/proxy-tests' 2>&1 | Tee-Object (Join-Path $inspectorEvidence 'proxy-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Inspector proxy tests failed.' }
    docker run --rm --network none --mount "type=bind,source=$inspectorRoot,target=/workspace" $inspectorImage sh -c 'cmake -S resident/inspector -B build/resident/inspector -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build/resident/inspector && for mod in vi_kernel vi_proxy control_inspector; do arm-vita-eabi-nm -u build/resident/inspector/$mod > build/resident/inspector/$mod-undefined.txt; arm-vita-eabi-readelf -hlSW build/resident/inspector/$mod.velf > build/resident/inspector/$mod-layout.txt; done' 2>&1 | Tee-Object (Join-Path $inspectorEvidence 'native-build.log')
    if ($LASTEXITCODE -ne 0) { throw 'Inspector ARM build failed.' }
    & $inspectorPython resident/inspector/verify_build.py --evidence $inspectorEvidence
    if ($LASTEXITCODE -ne 0) { throw 'Inspector artifact verification failed.' }
    & $inspectorPython resident/inspector/test_retire_session.py 2>&1 | Tee-Object (Join-Path $inspectorEvidence 'session-retirement-tests.log')
    if ($LASTEXITCODE -ne 0) { throw 'Inspector session retirement safeguards failed.' }
} finally { Pop-Location }
