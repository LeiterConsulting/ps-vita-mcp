# From a modded Vita to the developer preview

This is the supported staging path for further autonomous DevLoop work. It starts with an **already modded Vita** and ends with background inspection, verified file transfer, screen readback and bounded input, plus live Lua development in DevLoop. It does not install a firmware exploit or configure a storage adapter.

The development device runs firmware **3.65** with DevLoop **01.02**, Resident **0.1.1**, Control **0.3.3** and Starter **01.04**. Its unattended software tests have scoped evidence; physical touch and lifecycle gates remain open. Public DevLoop builds **01.03**, and all freshly built public packages need their own hardware acceptance. See [current qualification](QUALIFICATION.md) and [release gates](RELEASE-CHECKLIST.md). Building or staging a candidate does not certify a device.

## 1. Prepare the host and Vita

Use Windows, PowerShell 7, Python 3.13, Git and Docker Desktop with Linux containers. Have taiHEN/homebrew support working, the permissions needed to run unsafe homebrew enabled, and VitaShell or VitaDeploy's file manager available. Start from a normal boot with no old Control/Inspector kernel helper loaded. Keep a copy of your active tai configuration and important saves before changing the setup.

Enable WiFi using normal Vita settings. The PC and Vita must be reachable on the same trusted LAN. Read the actual USB drive letter or FTP address from the file manager; do not copy the development device's address. HTTP uses bearer tokens over unencrypted LAN transport. Do not expose these ports to the Internet.

```powershell
git clone https://github.com/LeiterConsulting/ps-vita-mcp.git
cd ps-vita-mcp
.\Setup-DevLoop.ps1
.\Build-McpBaseline.ps1
```

Setup creates a private checkout-local Python environment. The build runs host/simulated MCP/FTP tests and creates DevLoop, Resident, Starter and Input Target artifacts. It never contacts your Vita. Docker may download the digest-pinned SDK image initially; build containers use `--network none`.

Expected output:

| File | Purpose |
| --- | --- |
| `dist/devloop/vita_devloop.vpk` | Foreground Lua development host, title `CHRS00003` |
| `dist/resident/vita_resident.suprx` | Boot-loaded status/upload service |
| `dist/control/control_starter.vpk` | Starter app with its matched kernel/helper pair, title `CHRS00011` |
| `dist/workbench/input_target.vpk` | Disposable synthetic-input test app, title `CHRS00012` |
| Each component's `build-report.json` | Local artifact hashes, source fingerprint and validation |

No prebuilt binary release is implied by this guide. Build reports from this checkout identify your candidates. Preserve their hashes and reports for device acceptance. Complete linked-library notices before redistributing binaries.

## 2. Install and pair DevLoop

Follow [DevLoop installation and pairing](SETUP.md). In the file manager enable USB storage and identify its actual Windows drive letter:

```powershell
.\Stage-DevLoop.ps1 -DriveLetter F
```

Replace `F` with your device's letter. Use `-AllowUpdate` only when deliberately updating an existing DevLoop. The helper stages a VPK and a random pairing file at `ux0:data/vita-devloop/bridge.cfg`; it does not install the app. Safely disconnect USB, manually install the VPK in the file manager, and open DevLoop. Configure the displayed address:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure.py <Vita-IPv4>
.\.venv-devloop\Scripts\python.exe bridge\call_tool.py vita_status
```

Expect the correct app/version, fresh increasing frames and the matching bridge token. Keep `.devloop-private/` private. DevLoop's token is separate from Resident/Control's token.

## 3. Stage and activate Resident

Exit DevLoop and open the file manager's FTP server. Configure its displayed endpoint:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure_ftp.py <Vita-IPv4>:<FTP-port>
.\.venv-devloop\Scripts\python.exe resident\control\retire_session.py --inspect
```

The second command is read-only and reports the active configuration hash and any Control session marker. It is usable before installing Control. This path supports **`ur0:tai/config.txt` with no overriding `ux0:tai/config.txt`**. If inspection refuses your configuration layout, stop and adapt the procedure deliberately; do not remove your storage/plugin settings to satisfy it.

Use the **hash from your inspection**:

```powershell
.\.venv-devloop\Scripts\python.exe resident\stage.py --expected-config-sha256 <inspected-config-sha256>
```

For a first installation, staging creates a fresh Resident root, preserves the original configuration, generates Resident pairing, and verifies every uploaded file. It refuses an existing root/pairing or changed configuration. Read the printed receipt under `evidence/resident/`. In the file manager, copy the proposed setup folder's `config.txt` into `ur0:tai/`, then reboot normally. Keep `config.txt.before-resident` for rollback. **Resident has no installable bubble.** [Resident setup, updates and rollback](RESIDENT.md).

Expect Resident 0.1.1 to answer from LiveArea:

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_resident_status
```

Check its build ID against the local Resident build report. A successful FTP transfer or copied config alone does not prove activation.

## 4. Stage and start Control after boot

Reopen FTP after the reboot. Reinspect the config, whose hash changed when the Resident line was added. Keep Starter closed and verify that its session marker is absent:

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\retire_session.py --inspect
$controlBuild = Get-Content .\dist\control\build-report.json -Raw | ConvertFrom-Json
.\.venv-devloop\Scripts\python.exe resident\control\stage_starter.py `
  --sha256 $controlBuild.starter_package.sha256 `
  --expected-config-sha256 <new-inspected-config-sha256>
```

First-install FTP staging uploads only a fresh Starter VPK, with part and final readbacks. For an update over an older installed Starter, use `vita_workbench_stage_candidate` with `package: starter` and the exact VPK hash; boot Resident can stage it while Control is inactive. Installation remains manual. Do not retire an active session guard to satisfy a staging precondition. It does not alter boot config, pairing, installed apps or loaded modules. It requires matching Resident pairing and exact recorded source/package hashes. An unknown installed Starter is refused rather than overwritten.

Manually install the printed `ux0:data/vita-control/inbox/.../control_starter.vpk`. Reboot normally, open **Control Starter**, press **CROSS once**, and wait about ten seconds. Expect **MODULES LOADED**. Exit using **START + SELECT**. Control remains available after the app closes. Keep the installed matched pair together.

**Do not add the full Control pair to tai boot configuration.** The earlier boot activation hung and was recovered. This baseline loads Control only through the foreground Starter after a normal boot. The legacy `stage_control.py` command is disabled in the public checkout.

## 5. Connect the MCP client

Register two stdio servers using absolute paths from this checkout:

```json
{
  "mcpServers": {
    "vita_devloop": {
      "command": "C:/path/to/ps-vita-mcp/.venv-devloop/Scripts/python.exe",
      "args": ["C:/path/to/ps-vita-mcp/bridge/server.py"]
    },
    "vita_resident": {
      "command": "C:/path/to/ps-vita-mcp/.venv-devloop/Scripts/python.exe",
      "args": ["C:/path/to/ps-vita-mcp/resident/bridge.py"]
    }
  }
}
```

DevLoop exposes ten tools and resources. The combined Resident bridge exposes **four Resident, thirteen Control and ten Workbench tools**. Control uses the existing Resident token and port **17867**; Resident uses **17866**; foreground DevLoop uses **17865**. The desktop process speaks MCP; the Vita services speak authenticated HTTP.

Restart/refresh this client's existing MCP connection after updating the bridge. A long-lived old bridge rejected Control 0.2.2 as an unexpected identity until it was restarted. Restart the **PC connection**, not the loaded Vita modules. The supplied `resident/Register-Mcp.ps1` is an optional Codex CLI registration helper; other clients can use the JSON above.

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py list
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_control_status
```

For this pairing branch, expect Control 0.3.4, ABI 2, the local Control build ID, `lease_remaining_ms: 0`, and `keep_awake: false`.

## 6. Qualify this device before autonomous work

Run the explicit screen/file proof while the foreground is idle:

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\prove_device.py --label livearea --files
```

It records three previews, one detail frame, status and a fresh test text publication with verified readback. Inspect the images yourself. A label supplied on the command line is not proof of the actual foreground app. Your build ID must match, and frames/sequence must advance.

Open DevLoop and qualify hot reload with `bridge/prove_scripts.py`, or the minimal example in [SETUP.md](SETUP.md). For input, run the saved monitor while leaving physical controls neutral:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\mcp_input_proof.lua --resume --capture
```

Then capture the current PID before a bounded request. The monitor expects right+cross, both stick offsets and the two exact touch coordinates documented in [CONTROL.md](CONTROL.md). It should latch mask **31**, matching frames greater than zero, and `neutral_after: 1` after the lease expires. Read app telemetry as well as the Control receipt.

Install `dist/workbench/input_target.vpk` manually when ready to qualify synthetic controls. Open it, read `vita_workbench_target_status`, and call `vita_workbench_qualify_input` with the exact Control and Target build fingerprints. The test ends through Target self-exit; it does not simulate physical touch acceptance. Open paused native DevLoop for the hash-pinned Lua profiles described in [Workbench](../workbench/README.md).

Complete the [release acceptance checklist](RELEASE-CHECKLIST.md). Keep physical controller acceptance, screen inspection, sustained load and sleep recovery as separate results. Stop and collect logs if the device freezes, crashes, produces a persistent black screen or leaves input active. Do not automatically replay an uncertain change.

## 7. Resume after another reboot

Resident loads at boot; Control does **not**. Normal reboot unloads the Control pair but leaves `ux0:data/vita-control/control-session.lock` on storage. Keep Starter closed. After you have personally confirmed the normal reboot, inspect and retain that exact old marker:

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\retire_session.py --inspect
$controlBuild = Get-Content .\dist\control\build-report.json -Raw | ConvertFrom-Json
.\.venv-devloop\Scripts\python.exe resident\control\retire_session.py `
  --guard-sha256 <inspected-guard-sha256> `
  --package-sha256 $controlBuild.starter_package.sha256 `
  --expected-config-sha256 <inspected-config-sha256> `
  --normal-reboot-confirmed
```

This retains the marker under a fresh name after checking the exact installed Starter and unchanged config. It never unloads modules or changes boot config. **FTP availability is not reboot proof.** A failure/uncertain rename needs inspection before another action. Then open Starter, CROSS once, wait, exit, and read Control status again. Never remove an active marker to force a duplicate load.

For endpoint changes, update the `host` in the appropriate private JSON files while preserving their token and port; configure FTP separately. Requests reread the saved endpoint. For recovery, diagnostics and support reports, use [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Companion pairing candidate

The optional native pairing path builds Resident 0.1.2 and Starter 01.05 / Control 0.3.4. It requires manual installation and its own hardware gates. Follow [PAIRING.md](PAIRING.md); keep the desktop token private and keep the phone session separate from desktop input/work trials. The historical device acceptance above applies to the older installed builds.
