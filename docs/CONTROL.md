# Control service and MCP tools

Control 0.2.2 consists of a matched kernel helper and an authenticated user service in SceShell, activated by Control Starter 01.00. It runs independently of DevLoop after Starter exits. [Setup](GETTING-STARTED.md), [runtime qualification](BASELINE.md), [recovery](TROUBLESHOOTING.md).

## Service boundaries

| Service | Port | Pairing | Availability |
| --- | --- | --- | --- |
| Foreground DevLoop | 17865 | `.devloop-private/config.json` ↔ `ux0:data/vita-devloop/bridge.cfg` | DevLoop open |
| Resident | 17866 | `.devloop-private/resident.json` ↔ `ux0:data/vita-resident/bridge.cfg` | Loaded via Resident's `*main` entry after boot |
| Control | 17867 | Same Resident token | Starter loaded pair, until normal reboot |
| File manager FTP | Displayed by file manager | Separate FTP settings | User explicitly enabled it |

The combined desktop server is `resident/bridge.py`. Its four Resident tools remain available and its thirteen Control tools use the service below. Tokens are read on the PC; the loopback preview page receives no token.

## Tool reference

| Tool | Inputs / behavior |
| --- | --- |
| `vita_control_status` | No arguments. Identity, uptime, lease state and effective driver buttons/sticks. Check the expected fingerprint. |
| `vita_control_screen` | `detail` boolean. Returns PNG plus PID, dimensions, sequence, vblank, copy timestamps, hashes and round-trip timing. |
| `vita_control_input` | Current screen `target_pid`, `buttons`, `ttl_ms`, optional `left_stick`, `right_stick`, `front_touch`, `rear_touch`. Replaces the synthetic lease. |
| `vita_control_release` | Clears all synthetic state immediately. |
| `vita_control_list_files` | Optional 32-hex `attempt` and `offset`; pages of up to 32 revision directories/files. |
| `vita_control_file_info` | `attempt`, `name`; native size/hash. |
| `vita_control_read_text` | `attempt`, `name`, `expected_sha256`; verified UTF-8, at most 64 KiB. |
| `vita_control_write_text` | `name`, `text`; fresh revision, full readback twice. |
| `vita_control_publish_file` | `relative_file` relative to this checkout's `outgoing/`, exact `expected_sha256`; at most 8 MiB. |
| `vita_control_copy_file` | Source `attempt`, `name`, `expected_sha256`, `new_name`; fresh revision, source retained. |
| `vita_control_delete_file` | `attempt`, `name`, `expected_sha256`; deletes only an exact-hash managed file. |
| `vita_control_app` | `action` `launch`/`quit`, allowlisted `title_id` `CHRS00003`/`CHRS00009`. A native receipt needs separate screen/runtime observation. |
| `vita_control_sequence` | Latest `target_pid`, list of input steps. Up to 20 steps, at most five seconds total lease duration, 30-second execution budget. Before/after PNGs and trace retained; release in `finally`; stop on error/focus change. |

Known buttons are `up`, `down`, `left`, `right`, `cross`, `circle`, `square`, `triangle`, `l`, `r`, `start`, `select`. Sticks use integer pairs 0–255. Raw touch coordinate bounds are 0–1919 and 0–1087; normalized rear-panel coordinates can differ because the app uses panel calibration. Both contacts appear as synthetic ID 112 in the recorded trial. Physical contacts may also be present.

Leases last **16–1000 ms**, with an 8 ms kernel worker check and a two-sample emulation fallback. A changed displayed process cancels the lease. Analog requests are additive around center; use app readback and calibration for precision. Never infer delivery from the immediate input receipt alone.

The first five-channel trial used:

```json
{
  "target_pid": 12345,
  "buttons": ["right", "cross"],
  "ttl_ms": 800,
  "left_stick": [32, 224],
  "right_stick": [224, 32],
  "front_touch": [700, 400],
  "rear_touch": [1300, 700]
}
```

Replace `12345` with a fresh `vita_control_screen` PID while the input monitor is foreground. The saved [input monitor](../experiments/mcp_input_proof.lua) checks this exact request, records capability mask 31 and neutral return, and preserves its observed values after expiry. It is a synthetic delivery test, not a physical controller test.

With the monitor loaded and physical controls neutral, PowerShell 7 can submit that single lease through the real stdio server:

```powershell
$screen = .\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_control_screen | ConvertFrom-Json
$inputRequest = @{
  target_pid = [int]$screen.target_pid; buttons = @('right', 'cross'); ttl_ms = 800
  left_stick = @(32, 224); right_stick = @(224, 32)
  front_touch = @(700, 400); rear_touch = @(1300, 700)
} | ConvertTo-Json -Compress
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_control_input --arguments $inputRequest
.\.venv-devloop\Scripts\python.exe bridge\call_tool.py vita_script_status
```

Wait for expiry and inspect the app's latched metrics and a fresh Control status. Avoid touching the controls during the calibration/delivery check. Do not repeat a lost input reply automatically.

## Command-line diagnostics and preview

```powershell
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py list
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_control_status
.\.venv-devloop\Scripts\python.exe resident\control\call_tool.py vita_control_screen --save-images
.\.venv-devloop\Scripts\python.exe resident\control\preview.py
```

The preview prints a `http://127.0.0.1:<port>` URL. It polls 750 ms after each completed capture, pauses when hidden, and supports short inputs. It is not a streaming video guarantee. UI code has a simulated browser fixture; live device captures were qualified separately. Measure sustained rates and app overhead before using long sessions.

Workspace names use 1–63 ASCII letters/digits/underscore/dot/hyphen, excluding `.` and `..`. Attempts are fresh random 32-hex revisions. Copies use another revision rather than overwrite. Lost replies may represent completed writes: inspect the reported attempt/name/length/hash. Do not replay blindly.

## Native lifecycle and build identity

Starter loads the full kernel helper once, uses its own temporary bootstrap proxy to read exact readiness/caller/build metadata, releases that own-process proxy, then loads the Shell service with zero arguments. The service verifies the kernel ABI and fingerprint before listening. The fingerprint is SHA-256 over the ordered core source hashes in CMake and the verifier.

The Shell-caller guard protects input, capture and readback syscalls; the tiny readiness syscall is read-only. Four touch hooks and a lease worker initialize at runtime. Kernel/syscall modules are retained until reboot, with no forced hot unload. `control-session.lock` blocks duplicate submission across Starter app restarts. [Session reset procedure](GETTING-STARTED.md#7-resume-after-another-reboot).

`Build-Control.ps1` checks actual metadata/proxy/lease/HTTP C under host adapters, real MCP stdio against simulated HTTP, guarded FTP staging/retirement, native ARM imports/exports and SELF privilege isolation, and the exact eleven-entry Starter VPK including both MIT notices. Public packaging adds the original project license to the prototype's ten entries. This qualifies source/package behavior on the host; [BASELINE.md](BASELINE.md) records the distinct original hardware evidence.
