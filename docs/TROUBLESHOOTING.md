# Troubleshooting and recovery

Start by identifying which layer failed: host build, transfer, installation, startup, HTTP connection, MCP discovery, input delivery or application behavior. Keep the exact versions, hashes and logs. Builds and diagnostics should not change a live device unexpectedly.

**October 12, 2026:** both current experimental boot candidates are withdrawn from routine use. Diagnostic activation was followed by a boot hang/shutdown; its logs do not establish the resource trial or root cause. The test device's exact pre-experiment configuration was restored with two readbacks and both experiments disabled. The operator confirmed normal boot without L; fresh read-only configuration, disable-marker and registered Resident identity checks passed. Pairing and original attempt guards remain unchanged. Recovery is verified; it did not reactivate Control or qualify either boot candidate. Preserve evidence and do not re-arm either candidate.

| Symptom | Next check / action |
| --- | --- |
| No USB drive | Enable USB storage in VitaShell/VitaDeploy and use the actual mounted letter. Windows device detection alone is not a storage mount. |
| FTP unavailable | Open the file manager's FTP server and read its displayed IPv4/port. FTP is separate from the three HTTP ports. |
| Stage refused config layout | Inspect `ur0:tai/config.txt` and any overriding `ux0:tai/config.txt`. This setup supports the former without the latter. Preserve existing storage/plugin entries. |
| Resident proposal says no `*main` section | Preserve the original config and inspect its syntax. Staging requires an existing SceShell `*main` header with a line terminator. Deliberately add that section through the file manager if appropriate to your setup, then inspect the new hash before staging. |
| Resident staging says root/pairing exists | Inspect the existing deployment. First-install staging deliberately refuses reuse. Use the documented exact-plugin update path if updating Resident. |
| Package/source hash mismatch | Build the affected component again from this checkout. Do not edit a hash report to bypass drift checks. |
| Unknown installed Starter identity | The uploader accepts no installed Starter or exactly its current local build. An older/different Starter requires a separately reviewed update with its original package/config/logs retained and a normal reboot; this first-install helper cannot overwrite an unknown build. |
| Resident installed but unavailable | Confirm the proposed `*main` plugin path was copied into the active config, then normal reboot. Read `ux0:data/vita-resident/startup.log`. Match PC/device pairing and endpoint. |
| Starter says marker exists | A previous session marker remains. Do not rerun CROSS or delete it while modules may be loaded. Confirm normal reboot, inspect exact marker/config/package hashes, then use guarded retirement. |
| Starter loading/helper error | Stop further loads. Preserve `ux0:data/vita-control/<run>/starter.log` and `bootstrap.bin`, root `startup.log`, and the session marker. Normal reboot clears runtime modules; collect the error before changing anything else. |
| Infinite boot loading after legacy full Control entry | The supported baseline does not boot-load full Control. Recover the prior known configuration through the file manager. If normal boot is blocked, the tested device used the taiHEN L-button plugin bypass to reach recovery. Keep storage-plugin dependencies in mind; seek device-specific help if that path does not reach the file manager. Restore the original config and verify a normal boot before further tests. |
| Hang at the initial product-manual screen or shutdown after experimental boot activation | Stop activation attempts and preserve logs, opt-in and guards. On the test device, plugin-bypass boot reached the file manager. Restore the inspected pre-experiment configuration, preserving storage/plugin entries; a pre-diagnostic backup may still load Autostart. Disable both experiments and verify an ordinary boot before further work. The October 12 failure has no established root cause. |
| `Unexpected control endpoint identity` after bridge update | Restart/refresh the PC MCP connection so it reloads current Python source. A fresh stdio CLI call distinguishes an old client process from a device mismatch. Check the exact installed version, ABI and build report; the current pairing candidate is 0.3.4/ABI2. Do not hot reload Vita modules. |
| Tool list has only four Resident tools | Update the combined bridge and refresh its MCP connection. Current source server has 42 tools: thirteen Resident, thirteen Control and sixteen Workbench. Managed inbox inspection was introduced in Resident 0.1.4; the three native lifecycle tools require the 0.1.5 candidate and dedicated lab; [historical 0.1.4 qualification](managed-files-validation.json) and [current native incident](NATIVE-LIFECYCLE.md#october-12-native-promotion-incident) is separate from PC discovery. Run `resident/control/call_tool.py list`. |
| Wrong endpoint/authentication | Compare private host/port/token with the intended service. Resident/Control share one token; DevLoop uses a separate token. Preserve tokens when changing IP. Never paste them into an issue. |
| Black screen during app launch | A launch receipt is not runtime proof. Observe a fresh frame/PID after a bounded startup wait. A persistent black screen, crash or freeze needs logs and manual recovery, not repeated launch/input requests. |
| Preparation reports `runtime_ready_target_unverified` | The Lua endpoint is healthy but its native title/PID is missing or does not match the captured foreground. Script-only work can proceed; synthetic Workbench trials need installed native 01.04 identity and matching captures. Legacy 01.02/01.03 lacks this mapping. Do not treat a stable LiveArea PID as the app. |
| Preparation reports `runtime_ready_build_unpinned` | The native 01.04 target is mapped, but the caller omitted `expected_devloop_build`. Use the exact installed candidate's `nativeIdentity.buildId` or `package.buildId` from its build report for input readiness. Script-only work may proceed without this pin. |
| Preparation/trial says endpoint configuration changed | Finish or stop the current job before changing device configuration. Jobs freeze the foreground and effective Control endpoints, including port overrides; cleanup stays on the original endpoint. Inspect state and start a new operation rather than replay an uncertain launch/write. |
| One-shot automatic startup did not load Control | Keep this withdrawn candidate disabled. Inspect root `ux0:data/vita-autostart/startup.log`, `disabled`, `enable.once`, `enable.consumed`, `attempt.inflight` and the shared Control guard. Missing opt-in, prior guards, storage/hash/metadata errors and readiness timeout deliberately suppress loading. Preserve evidence; do not re-arm or run Starter on top of an uncertain attempt. |
| One-shot startup did not repeat after reboot | This candidate consumes its opt-in and retains guards. Persistent repeated-boot startup is not implemented. Do not delete markers to force another attempt while native state is uncertain. |
| HTTP 409 for input | Refresh the displayed PID; focus may have changed. Inspect lease state before a new request. |
| Receipt accepted but controls differ | Read the app's input telemetry. Sticks add to physical centers; calibrate. Touch support is one synthetic point per panel. Confirm the app reads the hooked APIs. |
| Long screen delay | Capture time and network round trip are different. Radio/network/app transitions produced multi-second delays in the record. Request sequentially; measure warm/cold behavior and avoid overlapping captures. |
| File publish timed out | Save the attempt/name/hash from the error or receipt. Read/stat that exact attempt. Do not replay an uncertain upload; partial files are retained. |
| Delete refused | The expected hash does not match the current managed file, or identity/path is invalid. Inspect it rather than broadening the path. |
| DevLoop change timed out | Read `vita_status` and `vita_script_status`. The recorded input monitor upload completed despite a lost reply, verified by source hash/revision. Use current state before another action. |
| Services unavailable after sleep | Wake the Vita and check WiFi/IP. Recheck identity and fresh status; wake recovery is still a separate qualification gate. The service does not prevent sleep. |

## Recovery boundaries

Resident rollback restores the saved pre-Resident tai config and uses a normal reboot. Preserve its staged files and pairing until recovery is verified. Control's manual runtime pair has no boot entry; normal reboot unloads it. A reboot does not remove its on-storage session marker. Retire that marker only through the exact-hash/installed-package checked procedure in [GETTING-STARTED.md](GETTING-STARTED.md).

For the withdrawn [one-shot startup experiment](AUTONOMOUS-DEVLOOP.md#experimental-one-shot-startup) and boot diagnostic, preserve configuration backups, setup files, logs and all attempt guards. Their `disabled` markers inhibit worker progression; they do not unload modules or prove that an early boot entry is harmless. Remove both experimental entries through an inspected rollback to the actual pre-experiment configuration, preserving storage and unrelated plugins. Do not delete opt-in/attempt markers to force a retry. Verify normal boot before considering manual Starter activation or any new trial. A successful module-loader receipt is not proof that the network service is active.

Do not force-unload syscall-exporting helpers, load a second pair into a running session, mix modules from different builds, or use the disabled legacy boot proposal. If an operation's result is uncertain, keep its evidence and inspect it before deciding the next action.

## Support report

Open an issue with:

- Component, source commit, app/bridge version, build ID and package SHA-256.
- Vita model/firmware, storage arrangement, relevant plugin names, host OS/Python/MCP client.
- Last confirmed good stage, exact reproduction, visible error, whether normal reboot occurred.
- Whether the result is a host fixture, package check, device API receipt, actual screen/app observation, or human physical input check.
- Sanitized logs and a minimal script if relevant.

Exclude pairing tokens, credentials, complete private configs, save data and proprietary game files. Local `evidence/`, `.devloop-private/` and `outgoing/` are not public artifacts. [Contributing](../CONTRIBUTING.md).
