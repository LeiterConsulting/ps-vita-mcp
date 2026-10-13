# From a modded Vita to the developer preview

This is the existing manual staging path for further autonomous DevLoop work. It starts with an **already modded Vita** and sets up background inspection, verified file transfer, screen readback and bounded input, plus live Lua development in DevLoop. It does not install a firmware exploit or configure a storage adapter. [Autonomous DevLoop status](AUTONOMOUS-DEVLOOP.md) separates the proven Control-free Lua loop from remaining native gates. Both experimental boot candidates were withdrawn after boot failures and remain disabled.

The test device runs firmware **3.65**. The corrected Resident **0.1.5** is currently boot-loaded after a confirmed normal boot and exact device-binary verification, with a fresh unblocked, installer-ready native instance and Promoter unloaded. Five fixed-Lab install/launch/evaluate/graceful-exit cycles across two native builds passed on hardware; same-build journal durability passed after a normal reboot without replay; the earlier unknown receipt is retained without replay. [Current incident](NATIVE-LIFECYCLE.md#october-12-native-promotion-incident). Historical Resident **0.1.4** passed a user-confirmed normal boot and 12 initial read-only inbox checks, including fresh 33-tool stdio MCP and direct native HTTP checks. Exact configuration/plugin readbacks preserved **0.1.3** and **0.1.2** rollback plugins, saved administrator pairing and both experiment disable markers. A separate 0.1.4 DevLoop coexistence check passed stable identity with advancing frames, a new 4096-byte upload, two complete publication readbacks and exact managed stat/readback. The earlier 0.1.3 Lua results remain historical. The legacy DevLoop launch broker remains disabled and refuses submission; repeated boot, storage durability across reboot and foreground/protected-UI launch policy remain pending. The earlier **0.1.2 / Control 0.3.4 / Starter 01.06** pairing results are historical, with no successful phone credential confirmation. [Managed-file qualification](MANAGED-FILES.md), [native gates](RESIDENT-LAUNCH-CANDIDATE.md), [pairing gates](PAIRING-DEVICE-TESTS.md).

DevLoop **01.04** is installed and passed exact native identity plus live Lua reload/recovery on the test device. Control capture mapping, synthetic input and sleep/reopen remain open. Legacy **01.02/01.03** lacks native mapping and is limited to script-only Workbench profiles. The older **0.1.1 / 0.3.3 / 01.04** qualification is historical. Source, build, installation and each hardware result remain separate evidence. See [qualification](QUALIFICATION.md) and [release gates](RELEASE-CHECKLIST.md). Building or staging does not certify a device. The earlier October 12 registered desktop MCP check exposed all 33 tools available at that point. Direct registered-tool calls passed exact installed Resident 0.1.4 status and managed listing/stat/full-file inspection; earlier fresh stdio checks remain separate evidence.

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

Current source builds the corrected Resident 0.1.5 candidate, now activated through a confirmed normal boot with its exact device binary verified. Its fresh native instance is unblocked and installer-ready; five fixed-Lab install/launch/evaluate/graceful-exit cycles across two native builds passed on hardware; same-build journal durability passed after a normal reboot without replay. Accepted 0.1.4 is retained for rollback. For a new activation, expect its matching version and build ID from LiveArea. A fresh normal boot requires its own qualification:

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

DevLoop exposes ten tools and resources. The combined Resident source bridge exposes **40 tools: eleven Resident, thirteen Control and sixteen Workbench**. Its three [native lifecycle candidate tools](NATIVE-LIFECYCLE.md) require Resident 0.1.5 and the dedicated lab; the accepted 0.1.4 service does not implement that namespace. Control uses the existing Resident token and port **17867**; Resident uses **17866**; foreground DevLoop uses **17865**; Lifecycle Lab uses **17868**; Resident 0.1.6 keep-awake uses **17869** ([lease guide](RESIDENT-KEEP-AWAKE.md)). The desktop process speaks MCP; the Vita services speak authenticated HTTP.

Restart/refresh this client's existing MCP connection after updating the bridge. A long-lived old bridge rejected Control 0.2.2 as an unexpected identity until it was restarted. Restart the **PC connection**, not the loaded Vita modules. The supplied `resident/Register-Mcp.ps1` is an optional Codex CLI registration helper; other clients can use the JSON above.

The October 12 refreshed registered MCP exposed all 36 tools and passed direct Resident 0.1.5 status, an unexecuted native preview and GET-only reconciliation of the completed post-reboot job. These checks added no native mutations. [Registered-client qualification](NATIVE-LIFECYCLE.md#registered-mcp-readiness-pass).

Before long synchronous soaks, configure an adequate per-tool timeout or use the CLI. The [PC guide](PC-SIDE.md#configure-the-bridges) gives Codex's `tool_timeout_sec = 4200` setting for the existing Resident entry; the soak limit remains 3,600 seconds.

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

Install `dist/workbench/input_target.vpk` manually when ready to qualify synthetic controls. Open it, read `vita_workbench_target_status`, and call `vita_workbench_qualify_input` with the exact Control and Target build fingerprints. The test ends through Target self-exit; it does not simulate physical touch acceptance. For Lua profiles, call `vita_workbench_prepare_devloop` with the exact installed Control pin. `ready_for_script_reload` permits a profile without input steps; `ready_for_input_trial` additionally requires the exact `expected_devloop_build` from the installed 01.04 build report and native DevLoop title/PID matching fresh captures. Legacy DevLoop lacks that mapping, so input-bearing Workbench profiles are blocked. The direct input-monitor example above is an operator-verified manual test, not an autonomous identity shortcut. [Workbench](../workbench/README.md).

Complete the [release acceptance checklist](RELEASE-CHECKLIST.md). Keep physical controller acceptance, screen inspection, sustained load and sleep recovery as separate results. Stop and collect logs if the device freezes, crashes, produces a persistent black screen or leaves input active. Do not automatically replay an uncertain change.

## 7. Resume after another reboot

In the manual path, Resident loads at boot and Control does **not**. Normal reboot unloads the Control pair but leaves `ux0:data/vita-control/control-session.lock` on storage. Keep Starter closed. After you have personally confirmed the normal reboot, inspect and retain that exact old marker:

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

For endpoint changes, update the `host` in the appropriate private JSON files while preserving their token and port; configure FTP separately. Start a new operation after updating configuration. Active preparation/trial jobs freeze their endpoints, detect drift and keep cleanup directed at the original endpoint. For recovery, diagnostics and support reports, use [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## 8. Separate experimental startup path

The [deferred startup helper](../resident/autostart/README.md) and isolated boot diagnostic are withdrawn from routine use after October 12 boot failures. Their default-disabled source and historical host/native results remain for offline diagnosis. Do not activate or re-arm these candidates or install direct full-Control boot entries. Preserve the recovered configuration, disable markers, rollback and possibly active guards. [Autonomous DevLoop](AUTONOMOUS-DEVLOOP.md) records the failed trials and verified recovery; the later Resident replacements used neither experiment.

## Companion pairing candidate

Current source builds the Resident 0.1.5 [native lifecycle candidate](NATIVE-LIFECYCLE.md) and Starter 01.06 / Control 0.3.4. Resident 0.1.5 adds installation and launch only for the dedicated Lifecycle Lab; five native Lab cycles across two builds passed, and same-build journal durability passed after a normal reboot without replay. Historical Resident 0.1.4 passed initial normal-boot, [managed inbox inspection](MANAGED-FILES.md) and DevLoop coexistence/upload checks. The earlier Resident 0.1.2 pairing trial passed startup, physical code display and graceful timeout; these are historical results. Resident 0.1.3's partial boot/identity/inventory/transfer results remain historical, with both 0.1.3 and 0.1.2 rollback plugins retained. Repeated boot, storage durability, successful phone credential confirmation and physical regression gates remain open. Follow [PAIRING.md](PAIRING.md); keep the desktop token private and keep the phone session separate from desktop input/work trials. Historical device acceptance does not transfer to a new build.
