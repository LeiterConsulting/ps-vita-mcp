# Troubleshooting and recovery

Start by identifying which layer failed: host build, transfer, installation, startup, HTTP connection, MCP discovery, input delivery or application behavior. Keep the exact versions, hashes and logs. Builds and diagnostics should not change a live device unexpectedly.

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
| `Unexpected control endpoint identity` after bridge update | Restart/refresh the PC MCP connection so it reloads current Python source. A fresh stdio CLI call distinguishes an old client process from a device mismatch. Check 0.2.2/ABI1 and the expected build ID. Do not hot reload Vita modules. |
| Tool list has only four Resident tools | Update the combined bridge and refresh its MCP connection. Current server has 17 tools. Run `resident/control/call_tool.py list`. |
| Wrong endpoint/authentication | Compare private host/port/token with the intended service. Resident/Control share one token; DevLoop uses a separate token. Preserve tokens when changing IP. Never paste them into an issue. |
| Black screen during app launch | A launch receipt is not runtime proof. Observe a fresh frame/PID after a bounded startup wait. A persistent black screen, crash or freeze needs logs and manual recovery, not repeated launch/input requests. |
| HTTP 409 for input | Refresh the displayed PID; focus may have changed. Inspect lease state before a new request. |
| Receipt accepted but controls differ | Read the app's input telemetry. Sticks add to physical centers; calibrate. Touch support is one synthetic point per panel. Confirm the app reads the hooked APIs. |
| Long screen delay | Capture time and network round trip are different. Radio/network/app transitions produced multi-second delays in the record. Request sequentially; measure warm/cold behavior and avoid overlapping captures. |
| File publish timed out | Save the attempt/name/hash from the error or receipt. Read/stat that exact attempt. Do not replay an uncertain upload; partial files are retained. |
| Delete refused | The expected hash does not match the current managed file, or identity/path is invalid. Inspect it rather than broadening the path. |
| DevLoop change timed out | Read `vita_status` and `vita_script_status`. The recorded input monitor upload completed despite a lost reply, verified by source hash/revision. Use current state before another action. |
| Services unavailable after sleep | Wake the Vita and check WiFi/IP. Recheck identity and fresh status; wake recovery is still a separate qualification gate. The service does not prevent sleep. |

## Recovery boundaries

Resident rollback restores the saved pre-Resident tai config and uses a normal reboot. Preserve its staged files and pairing until recovery is verified. Control's runtime pair has no boot entry; normal reboot unloads it. A reboot does not remove its on-storage session marker. Retain that marker only through the exact-hash/installed-package checked procedure in [GETTING-STARTED.md](GETTING-STARTED.md).

Do not force-unload syscall-exporting helpers, load a second pair into a running session, mix modules from different builds, or use the disabled legacy boot proposal. If an operation's result is uncertain, keep its evidence and inspect it before deciding the next action.

## Support report

Open an issue with:

- Component, source commit, app/bridge version, build ID and package SHA-256.
- Vita model/firmware, storage arrangement, relevant plugin names, host OS/Python/MCP client.
- Last confirmed good stage, exact reproduction, visible error, whether normal reboot occurred.
- Whether the result is a host fixture, package check, device API receipt, actual screen/app observation, or human physical input check.
- Sanitized logs and a minimal script if relevant.

Exclude pairing tokens, credentials, complete private configs, save data and proprietary game files. Local `evidence/`, `.devloop-private/` and `outgoing/` are not public artifacts. [Contributing](../CONTRIBUTING.md).
