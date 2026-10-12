# PC setup and development workflows

This repository publishes the Windows PC bridges, development runners, build scripts and Vita services. The iPhone application is developed and distributed privately; its [public guide](IPHONE-COMPANION.md) describes use without shipping app source. As of October 12, 2026, the developer preview adds Control-free foreground Lua iteration. Both experimental boot candidates are withdrawn and the recovered startup configuration is verified. [Autonomous development status](AUTONOMOUS-DEVLOOP.md), pairing and physical [hardware gates](PAIRING-DEVICE-TESTS.md) remain separate.

## Public components

| Location | Purpose |
| --- | --- |
| `bridge/` | Ten foreground DevLoop MCP tools, configuration, FTP staging, Lua edit/run/capture and explicit live proof helpers |
| `resident/bridge.py` | Combined 30-tool PC server: four Resident, thirteen Control and thirteen Workbench tools |
| `resident/control/` | PC Control adapter, screen preview/decoding, guarded staging and recovery, plus matched native modules |
| `resident/autostart/`, `resident/boot_diagnostic/` | Withdrawn default-disabled boot experiments, retained for offline diagnosis |
| `resident/launch_client.py`, `resident/launch_broker/` | Control-free preparation client and fixed-title launch contract; installed 0.1.3 has partial native qualification, with launching disabled and refused |
| `workbench/` | Shared session lock, bounded Control-free candidate sessions, Control-backed trials, metrics, restoration, file verification and activity/lifecycle observers |
| `tools/prove_script_session.py` | Explicit live stdio MCP demonstration: prepare, evaluate two Lua candidates, rank and restore |
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

After updating PC source, restart the relevant PC MCP connection to discover the combined 30-tool catalog. The existing two stdio entries remain sufficient; the new script tools are part of the Resident PC bridge, and the separate DevLoop bridge still has ten tools. Do not reload Vita helpers to refresh desktop tools. `resident/Register-Mcp.ps1` is the optional Codex CLI registration helper; a different existing registration is refused rather than silently replaced. [Troubleshooting](TROUBLESHOOTING.md) covers offline services, identity mismatch and reboot guards.

Synchronous MCP jobs can outlast the client's per-tool timeout, including script sessions and long soaks. Codex supports `tool_timeout_sec` and defaults to 60 seconds. Add `tool_timeout_sec = 4200` inside the existing `[mcp_servers.vita_resident]` table in `~/.codex/config.toml`, retaining its transport settings, then refresh the PC connection. This allows the supported maximum 3,600-second soak plus request and cleanup time; it does not raise any job limit. Other MCP clients need an adequate timeout or the CLI. [Official OpenAI MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

For long sessions, run `.\.venv-devloop\Scripts\python.exe -m workbench.cli soak 600 <Control-build-ID>` from the checkout. CLI jobs retain journals under `evidence/workbench/`; inspect the recorded result and cleanup receipt after an interruption before starting another job.

## Run and recover development work

For Lua iteration without Control, open the installed, paired DevLoop 01.04 and leave it paused. Pin the report matching the installed native app:

```powershell
$devloop = Get-Content .\dist\devloop\build-report.json -Raw | ConvertFrom-Json
.\.venv-devloop\Scripts\python.exe -m workbench.cli prepare-script $devloop.nativeIdentity.buildId
```

This calls `vita_workbench_prepare_script_session` and returns fresh native PID/run/revision pins after two healthy paused observations. It does not need Control or a Resident launch broker. Use those pins in a UTF-8 JSON manifest with `candidates`, `expected_devloop_build`, `expected_pid`, `expected_run`, `expected_revision`, and optional `retain_best`/`selection`. Each candidate carries inline source, its exact UTF-8 `source_sha256` and finite metric checks. Submit the exact manifest hash:

```powershell
$manifestHash = (Get-FileHash .\outgoing\script-session.json -Algorithm SHA256).Hash.ToLowerInvariant()
.\.venv-devloop\Scripts\python.exe -m workbench.cli script-session .\outgoing\script-session.json $manifestHash
```

For a ready-made explicit live demonstration, `tools/prove_script_session.py <DevLoop-native-build-ID>` uses a fresh stdio MCP to prepare, generate/hash two moving scenes, measure/rank their movement rates and restore the original scene paused. Optional `--retain-best` leaves the winner fresh and paused. Both corrected default and retention proofs passed on the installed Vita on October 12, with exact runtime identity. Default restoration and separate guarded cleanup after retention restored the original scene/native world paused. The first cumulative-distance ranking proof failed due unequal execution time and is retained, along with a reconciled PC cleanup-journal failure. See [Workbench](../workbench/README.md#control-free-script-sessions) for candidate bounds, manifest fields and journals. These jobs have no remote scene lease, capture, synthetic input or keep-awake; do not rely on PC activity to prevent Vita sleep. Lost replies are never replayed, and uncertain ownership can leave restoration unconfirmed. The proofs qualify this bounded script loop and explicit retention, not full autonomous platform operation.

The optional preparation launch branch is a future adapter contract: `prepare-script` defaults to no launch, and `--allow-launch` also requires exact `--resident-build` and `--resident-instance` pins. Resident 0.1.3 is installed and passed normal boot, native identity/clock and file-manager inventory checks. Eight read-only observations then matched inventory's DevLoop PID to its stable exact runtime while frames and Resident time advanced. Fresh stdio MCP status and 4 KiB probes with two readbacks passed with both apps open at separate times, without restarting Resident. A new two-candidate Lua regression also passed under 0.1.3, selecting the rate-120 candidate and restoring the original native world paused; Lua finished inactive with the last VM retained. Native submission is unconditionally refused. A fresh stdio process verified the 30-tool catalog and 0.1.3 status, but the registered desktop connection remains an older 28-tool process that rejects 0.1.3; refresh it from the updated checkout. Resident 0.1.2 is retained for rollback and lacks the broker namespace. [Native qualification and remaining hardware gates](RESIDENT-LAUNCH-CANDIDATE.md). Open DevLoop manually; storage durability across reboot, foreground/protected-UI qualification and phone credential confirmation remain pending. Running the PC script tools does not stage or activate native packages.

For Control-backed work, use the separate workflow below. Its `prepare` positional build is the **Control** build, unlike `prepare-script`'s **DevLoop** build.

Start with `vita_workbench_doctor` to inspect availability and the exact Control build. `vita_workbench_prepare_devloop` can launch DevLoop once when its endpoint is unavailable and inspect readiness without replacing a scene. It defaults to DevLoop 01.04, which publishes native title/PID, run and source-build identity. Healthy paused runtime gives `ready_for_script_reload`; input readiness/trials additionally require `expected_devloop_build` matching the actual build report and native `CHRS00003` title/PID matching fresh captures. The build pin is optional for script-only 01.04 work. Select 01.02 or 01.03 explicitly for legacy script-only work. Legacy versions lack this mapping. The installed 01.04 passed exact runtime identity and live Lua reload/recovery; Control capture mapping, synthetic input and lifecycle gates remain open. Background status/control can remain available after Starter exits, until normal reboot.

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\bounce.lua --resume --capture
```

Workbench trials pin profile/source hashes and native build identity, record mutation intent before device changes, and retain metrics and cleanup receipts. Preparation and trials freeze their foreground and effective Control endpoints, including `VITA_CONTROL_PORT`; detected configuration drift stops work while cleanup stays on the original endpoint. Input-bearing profiles fail before scene mutation without native target mapping and recheck that mapping before each step. Use [Workbench](../workbench/README.md) for script-only profiles, qualified input trials, capture soak, observers and managed-file recovery. Live proof helpers perform device actions only when explicitly invoked; coordinate an idle device and check their scope first.

The normal Starter path remains manual once per confirmed boot and inspected native state. [Deferred automatic startup](AUTONOMOUS-DEVLOOP.md#experimental-one-shot-startup) and its isolated diagnostic are withdrawn from routine use after boot failures; keep both disabled and preserve the verified recovery. Neither a PC restart nor a successful host build activates or qualifies a boot candidate. Native installation, boot acceptance and recovery remain operator steps. Repeated-boot operation is not implemented or qualified.

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
