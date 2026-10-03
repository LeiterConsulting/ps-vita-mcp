# Read-only app and Shell diagnostics

Control Inspector **01.03**, title ID **CHRS00010**, tests a small kernel metadata helper from its own app and from a temporary proxy inside SceShell. It checks ABI, build identity, caller identity, the Shell permission guard and exact invalid-argument/permission error values.

On October 3, 2026, the development 01.03 package passed both checks on one homebrew-enabled firmware-3.65 Vita. Both user proxies stopped/unloaded successfully and the app exited normally. The tiny syscall-exporting kernel helper remains loaded until a normal reboot. [Exact prototype identities and scoped results](resident-inspector-prototype-validation.json).

These checks establish the read-only handoff. Input injection, framebuffer capture, networking inside Inspector and the broader Control service are outside this test.

## Build and first run

```powershell
.\Setup-DevLoop.ps1
.\Build-Inspector.ps1
```

The build runs the actual metadata and proxy C implementations under sanitizers with SDK/file adapters, then validates native imports/exports, SELF authority, the shared source fingerprint and VPK contents. A local FTP fixture verifies session-retirement failure handling. Building does not contact the Vita.

Copy `dist/inspector/control_inspector.vpk` through your file manager's USB/FTP transfer and install it manually. The package contains the app, metadata kernel helper and diagnostic proxy. It does not add boot configuration entries.

For the first test, start from a normal reboot, with no earlier Inspector helper loaded:

1. Open Control Inspector and press **CROSS** once.
2. Wait for **APP: PASS**. If it fails, exit and inspect the logs before another attempt.
3. Press **SQUARE** once, wait for **SYSTEM SHELL: PASS**, then exit with **START + SELECT**.
4. Reopen the file manager to collect the report directory under `ux0:data/vita-control-inspector/`.

The Shell proxy starts with zero argument bytes and reads the freshly written, validated 44-byte session record. It verifies the Shell caller and publishes its report only after a complete write/close. The app waits for a completion marker with the exact build ID and fresh run nonce before unloading the proxy. A timeout leaves the read-only proxy loaded until reboot.

## Another run or an update

Inspector writes `ux0:data/vita-control-inspector/kernel-session.lock` before loading its helper. That marker prevents a second helper load in another app session. **A normal reboot clears loaded modules but leaves the marker on storage.** Keep Inspector closed while inspecting and retiring that marker.

After any manual package update, reboot normally and open FTP. Configure FTP with the endpoint shown by the file manager, then perform a read-only inspection:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure_ftp.py <Vita-IPv4-address>:<FTP-port>
.\.venv-devloop\Scripts\python.exe resident\inspector\retire_session.py --inspect
```

The output gives the exact guard and active configuration hashes. It does not infer a reboot from FTP availability. After confirming the normal reboot yourself, retire the inspected marker:

```powershell
$build = Get-Content .\dist\inspector\build-report.json -Raw | ConvertFrom-Json
.\.venv-devloop\Scripts\python.exe resident\inspector\retire_session.py `
  --guard-sha256 <inspected-guard-sha256> `
  --package-sha256 $build.package.sha256 `
  --expected-config-sha256 <inspected-active-config-sha256> `
  --normal-reboot-confirmed
```

This verifies the four installed app/module/SFO files against the exact local package, checks the active config and marker, renames the marker to a unique retained name and verifies both resulting paths. It does not stop/start modules or edit the boot configuration. If the outcome is uncertain, inspect the retained receipt and exact paths before any retry.

Public retirement tooling accepts the user's inspected configuration hash instead of a development-device hash. Rebuilt public packages retain their own source/package identities; the archived prototype package hash does not certify a new package or a new device.
