# PC setup and development workflows

This repository publishes the Windows PC bridges, development runners, build scripts and Vita services. The iPhone application is developed and distributed privately; its [public guide](IPHONE-COMPANION.md) describes use without shipping app source. As of October 5, 2026, development and device testing are paused. The latest source is available as a developer preview, with the [remaining hardware gates](PAIRING-DEVICE-TESTS.md) recorded separately.

## Public components

| Location | Purpose |
| --- | --- |
| `bridge/` | Ten foreground DevLoop MCP tools, configuration, FTP staging, Lua edit/run/capture and explicit live proof helpers |
| `resident/bridge.py` | Combined 27-tool PC server: four Resident, thirteen Control and ten Workbench tools |
| `resident/control/` | PC Control adapter, screen preview/decoding, guarded staging and recovery, plus matched native modules |
| `workbench/` | Shared session lock, hash-pinned trials, metrics, restoration, file verification and activity/lifecycle observers |
| `tools/pairing_check.py` | Local PC form for physical code confirmation and inspection-permission qualification |
| `scripts/`, `tests/`, component test files | Source/build validation, local HTTP/FTP fixtures, sanitizer harnesses and CI |
| `Build-*.ps1`, `Setup-DevLoop.ps1`, `Stage-DevLoop.ps1` | Reproducible PC environment, native builds and explicit manual-install staging |
| `docs/`, examples and manifests | Setup, protocols, measured limits, sanitized acceptance records and recovery |

Raw journals, tokens, FTP settings, captured frames, generated packages and local virtual environments are excluded from Git. The historical backup and game-port experiments are separate workspace activities, outside the MCP product source.

## Prepare a PC checkout

The documented host uses Windows, PowerShell 7, Python 3.13, Git and Docker Desktop with Linux containers. The dependency lock and SDK image digest are checked into the repository. Other host/device combinations have not completed the same acceptance.

```powershell
git clone https://github.com/LeiterConsulting/ps-vita-mcp.git
cd ps-vita-mcp
.\Setup-DevLoop.ps1
.\Build-McpBaseline.ps1
```

Builds use host adapters and local fixtures; they do not contact a Vita. `dist/` contains generated packages and build reports. Each native report records the relevant source hashes and artifact identities. Building successfully does not install or qualify those packages. Follow [Getting started](GETTING-STARTED.md) for manual staging, installation, normal reboot, one-time Starter activation and rollback.

## Configure the bridges

Use absolute executable and script paths when registering the two stdio MCP servers, as shown in [Getting started](GETTING-STARTED.md#5-connect-the-mcp-client). Keep each bridge pointed at the intended checkout and private configuration; updating a clone does not update a running MCP process automatically.

| Local configuration | Used by |
| --- | --- |
| `.devloop-private/config.json` | Foreground DevLoop bridge; `VITA_DEVLOOP_CONFIG` can select another private file |
| `.devloop-private/resident.json` | Resident and Control bridge; `VITA_RESIDENT_CONFIG` can select another private file |
| `.devloop-private/ftp.json` | Explicit file-manager FTP staging, configured by the setup/staging helpers |
| `.devloop-private/workbench.lock` | Shared desktop operation lock; `VITA_WORKBENCH_LOCK` selects an intentional common path |

DevLoop normally listens on 17865, Resident on 17866 and Control on 17867. The file manager's FTP port is separate. Control shares the Resident administrator token; the foreground DevLoop token is a separate pairing. Keep all credentials local. Services use unencrypted HTTP on a trusted LAN.

After updating PC source, restart the relevant PC MCP connection. Do not reload Vita helpers to refresh desktop tools. `resident/Register-Mcp.ps1` is the optional Codex CLI registration helper; a different existing registration is refused rather than silently replaced. [Troubleshooting](TROUBLESHOOTING.md) covers offline services, identity mismatch and reboot guards.

## Run and recover development work

Start with `vita_workbench_doctor` to inspect availability and the exact Control build. Foreground Lua operations require DevLoop open; background status/control can remain available after Starter exits, until normal reboot.

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\bounce.lua --resume --capture
```

Workbench trials pin profile/source hashes and native build identity, record mutation intent before device changes, and retain metrics and cleanup receipts. Use [Workbench](../workbench/README.md) for the smoke/input profiles, capture soak, activity observers and managed-file recovery. Live proof helpers perform device actions only when explicitly invoked; coordinate an idle device and check their scope first.

After an interrupted upload, retain its attempt ID, expected size and hash. `vita_resident_verify_upload` reads that exact attempt twice. The candidate staging repair now uses one ID across journal, upload and receipt; a lost reply is not automatically replayed. Native installation is still manual.

## Test native pairing from the PC

The standalone form reproduces a Companion-style exchange from the PC without needing iPhone app source. This is an explicit hardware qualification utility, separate from MCP startup. Its default live target is Resident 0.1.2 / Control 0.3.4 on ports 17866/17867; the operator supplies exact installed build IDs.

First run the offline checks:

```powershell
.\.venv-devloop\Scripts\python.exe tools\pairing_check.py --self-test
```

For an explicitly scheduled device trial, verify that the installed native files match your reports, the services are idle, and the administrator pairing is present. Then start the form with those pins:

```powershell
$resident = Get-Content .\dist\resident\build-report.json -Raw | ConvertFrom-Json
$control = Get-Content .\dist\control\build-report.json -Raw | ConvertFrom-Json
.\.venv-devloop\Scripts\python.exe tools\pairing_check.py `
  --resident-build $resident.plugin.build_id --control-build $control.build_id
```

Open the printed `127.0.0.1` URL on that PC. Open SQUARE pairing in the already loaded Starter, select **Start test request** on the PC, release Vita controls briefly, press CROSS once, and enter the six-digit code directly into the form. Keep Starter open until confirmation finishes. The original 120-second deadline starts when the request is created; moving a code through chat introduces avoidable delay. Do not run the module-load action again in the same boot.

The utility verifies exact idle service identities before requesting pairing. On success it saves the individual credential only under `.devloop-private/`, checks session/status access, expects five file/input/power/launch requests to return 403, and verifies independent Windows access and neutral leases. Those denied requests are part of the live trial. The generic report contains statuses and credential identifiers, never a code or token. If a response is rejected or lost, the form stops without replay; inspect the report before a new trial.

The form binds only to loopback, uses a per-run URL and anti-forgery token, and stops after 30 minutes or Ctrl+C. It does not acquire a work/input lease, capture the pairing screen, or keep the Vita awake. Its offline self-tests do not establish native confirmation, persistence or physical acceptance. The previous private form was stopped before sending a new request, so those device gates remain pending.

## Check publication scope

```powershell
.\.venv-devloop\Scripts\python.exe scripts\check_public_scope.py
```

CI runs this audit, the pairing form self-tests and the portable C/MCP contracts. The scope audit rejects tracked private phone files, signing/build artifacts, credentials directories and generated evidence, including files force-added through `.gitignore`. It checks paths; review file contents and history separately before publication. [Contributing](../CONTRIBUTING.md#public-source-and-private-phone-app) describes the boundary.
