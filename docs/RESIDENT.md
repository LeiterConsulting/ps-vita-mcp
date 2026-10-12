# Background status and verified uploads

Vita Resident 0.1.2 is a separate SceShell user plugin. It exposes device status, a bounded upload inbox and the native individual-pairing authority while a foreground app runs. The desktop MCP server is `resident/bridge.py`; the native service uses port **17866**. The candidate is installed with startup and pairing-window exchange verified; its exact identity was verified through the registered MCP after the recovered normal boot on October 12. Successful individual confirmation remains pending. [Pairing contract and device gates](PAIRING.md).

The earlier 0.1.1 development prototype passed status and storage checks on one homebrew-enabled Vita running firmware 3.65, including a 4 KiB probe and a 1.2 MB package with the file manager in the foreground. Those results do not qualify the new pairing authority. Gameplay coexistence, sustained transfer load and sleep/wake recovery still need separate checks. [Historical scope and identities](resident-inspector-prototype-validation.json).

## Build

From the repository root, with Docker Desktop running:

```powershell
.\Setup-DevLoop.ps1
.\Build-Resident.ps1
```

The current source builds the disabled 0.1.3 qualification candidate. The build runs the actual C HTTP/storage service under sanitizers with host adapters, MCP stdio fixtures, first-install FTP fixtures and update fixtures. It validates the ARM module's identity, imports, lifecycle, unresolved symbols and source fingerprint. Outputs are `dist/resident/vita_resident.suprx` and `dist/resident/build-report.json`. Building does not contact the Vita.

The combined public bridge exposes four Resident tools, thirteen [Control tools](CONTROL.md) and thirteen [Workbench tools](../workbench/README.md), for 30 total. The two new script-preparation/session tools run on the PC through the existing foreground DevLoop API; they do not add native capabilities to installed Resident. The Resident MCP subset retains these four operations:

| Tool | Operation |
| --- | --- |
| `vita_resident_status` | Read heartbeat, service instance, battery, clocks and network state |
| `vita_resident_probe_upload` | Publish a fixed 4 KiB probe into a fresh inbox attempt |
| `vita_resident_stage_package` | Validate and publish the local DevLoop VPK using its exact SHA-256 |
| `vita_resident_verify_upload` | Read a named published package/probe twice and verify its length/hash |

Package uploads are limited to **8 MiB**. The service writes a fresh `.part`, verifies its stored hash and renames it to the final name. The bridge then performs two complete readbacks. A failed reply may leave a completed upload: verify its reported attempt before deciding what to do next. Uploads are never automatically replayed, and installation remains manual.

## Control-free scripts and launch candidate

An already open, healthy paused DevLoop 01.04 supports `vita_workbench_prepare_script_session` and `vita_workbench_script_session` without Control or a Resident launch broker. Exact native build/PID/run/revision pins bind up to eight hashed Lua candidates to that runtime. The runner measures finite metrics, ranks accepted candidates and restores the original paused VM between runs; explicit `retain_best` reloads the selected source fresh and paused. It has no work/input lease, power tick, keep-awake, capture or native installation. [Workbench workflow](../workbench/README.md#control-free-script-sessions).

The corrected default and explicit-retention two-candidate script proofs passed on the installed Vita on October 12, with stable exact identity and rate-based selection. Default restoration and separate guarded cleanup after retention restored the original paused scene/native world. The initial cumulative-distance ranking assertion failed due unequal execution times and is retained, along with a reconciled PC cleanup-journal failure. This proves foreground script iteration through the existing API, not a new native Resident capability or physical-control acceptance.

The separate [launch broker](../resident/launch_broker/README.md) and `resident/launch_client.py` now have a disabled Resident 0.1.3 native qualification build. Its exact native identity, immutable attempt store, strict HTTP namespace and read-only app inventory reuse the existing worker. Native submission is unconditionally refused; no boot dispatch, enable file, additional boot plugin or launch import exists. It is not installed. Resident 0.1.2 has no broker namespace, so the current system still requires someone to open DevLoop.

The future launch branch defaults off, requires explicit `allow_launch` plus exact Resident build/instance pins, and submits at most one fixed `CHRS00003` attempt after durable journaling. Lost replies are inspected without replay. [The 0.1.3 hardware sequence](RESIDENT-LAUNCH-CANDIDATE.md) separates native boot/storage/identity/inventory checks from the later foreground-policy and launch qualification. Building or host testing this candidate changes no installed native files or startup configuration and uses neither withdrawn boot experiment.

## Stage and activate

This prototype loads at boot. Coordinate availability for installation and recovery. Inspect the actual active taiHEN configuration first; the current staging tool supports `ur0:tai/config.txt` with no overriding `ux0:tai/config.txt`. Keep a copy of the original configuration. Use its SHA-256, not a value from someone else's device.

Open the Vita file manager's FTP server and configure its displayed endpoint:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure_ftp.py <Vita-IPv4-address>:<FTP-port>
.\.venv-devloop\Scripts\python.exe resident\stage.py --expected-config-sha256 <active-config-sha256>
```

Staging preserves the active configuration and creates a fresh setup directory, pairing file, inbox, configuration proposal and rollback copy. Files receive temporary and final readback checks. The exact paths and hashes appear in the local deployment receipt under `evidence/resident/`.

To activate manually, copy the staged setup folder's **config.txt** into **ur0:tai/**, replacing the active file, then reboot normally. There is no Resident VPK/bubble. Keep its `config.txt.before-resident` backup and the staged plugin files. Startup diagnostics are saved to `ux0:data/vita-resident/startup.log` with a 2 KiB bound and no pairing token.

To roll back, restore that original configuration through the file manager and reboot normally. Do not hot-unload or refresh the plugin: if it supplied the shared network pool, that pool must survive until SceShell exits.

The stage command creates `.devloop-private/resident.json`. Configure an additional MCP stdio server using absolute checkout paths:

```json
{
  "mcpServers": {
    "vita-resident": {
      "command": "C:/path/to/ps-vita-mcp/.venv-devloop/Scripts/python.exe",
      "args": ["C:/path/to/ps-vita-mcp/resident/bridge.py"]
    }
  }
}
```

DevLoop and Resident have separate native services, ports and pairing configurations. Resident uses unencrypted HTTP on a trusted LAN. It does not change sleep settings; true sleep or network loss can make it unavailable. Heartbeat and requests are sequential, so an upload can delay status responses.

## Updates and live qualification

`resident/stage_update.py` replaces exactly one inspected Resident configuration entry in a proposal, preserving pairing and all other configuration bytes. Its `--expected-config-sha256` and `--old-plugin` arguments bind the update to the inspected state. Activation remains a manual config copy and normal reboot.

`resident/prove_device.py` performs live actions only when explicitly run. It can collect status continuity, publish a probe or stage DevLoop, and record a user-supplied foreground label. That label does not establish which application is on screen. A restarted service fails a continuity claim. Test physical responsiveness and wake recovery separately.

The combined desktop bridge also exposes Control for bounded synthetic input, cross-app framebuffer readback and managed files. [Control tools](CONTROL.md) and the [functional baseline](BASELINE.md) document the recorded results and limits. Automatic native installation is not implemented. The manual Starter path remains available after a confirmed normal boot and inspected native state. The separate [one-shot startup experiment](../resident/autostart/README.md) and isolated boot diagnostic are withdrawn after boot failures; both remain disabled, and recovered Resident operation is verified. Their source/host results do not qualify a new boot attempt or replace Resident. [Autonomous DevLoop](AUTONOMOUS-DEVLOOP.md) explains script/input readiness and the recovery. For the complete manual Resident/Starter/DevLoop path, use [GETTING-STARTED.md](GETTING-STARTED.md).
