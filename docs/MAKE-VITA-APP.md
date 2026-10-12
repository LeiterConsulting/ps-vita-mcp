# Make Vita App

The [`make-vita-app` skill](../skills/make-vita-app/SKILL.md) turns a request such as
“make a paddle game for Vita” into a project, behavior checks, build/runtime
evidence and an iteration workflow. `make_vita_app` is also described as a natural
trigger; the canonical Codex invocation uses hyphens:

> Use $make-vita-app to make a paddle game for Vita and test it through MCP.

> Use $make-vita-app to plan a port of this application to Vita. Plan only.

> Use $make-vita-app to inspect this source port and implement its smallest
> representative Vita prototype.

The skill preserves planning versus implementation intent. It does not claim
general Android support, automatic port conversion, arbitrary-title installation
or that numerical tests replace human visual/physical acceptance.

## Install and use

From a configured checkout, install the skill into the local Codex skill directory:

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py install-skill
```

The installer refuses to overwrite an existing skill. It writes a local
`repository.json` pointing to this checkout; that workstation path is not part of
the public skill. Start a fresh chat or refresh skill discovery if the client
caches its catalog. The installed launcher also accepts `VITA_APP_REPO`, and the
repository copy can discover the checkout from the current directory.

The skill files and project helper are public. Generated projects default to
`.devloop-private/vita-apps/<slug>/`; evidence, credentials and local configuration
remain ignored. Move selected original source into a suitable public project only
when publication is intended. iPhone implementation/build/signing material stays
private.

## Delivery routes

| Route | Deliverable | Current automation boundary |
| --- | --- | --- |
| Plan / port assessment | Source/dependency/asset analysis, measurable slice, acceptance plan | No implementation/device mutation for plan-only requests |
| Lua | Source scene inside DevLoop 01.04 | Automatic reload/run/evaluate/restore once DevLoop is open and paused |
| Native development slot | Compiled prototype in the single owned `VMCP00001` bubble | Existing Resident install/launch/self-test/exit loop; one candidate at a time |
| Standalone native title | Separate application/package | Requires its own qualified title/package/runtime adapter |

The pristine `lifecycle_lab/` baseline and its five-cycle qualification remain
unchanged. The independent `app_slot/` wrapper reuses the authenticated lifecycle
core, HTTP service and platform adapter. It compiles a project module with its own
source fingerprint and application self-test into the owned development slot.
This is deliberate slot-based development, not a relabeled third-party VPK.

## Lua project

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py new paddle --route lua --name "Vita Paddle"
.\.venv-devloop\Scripts\python.exe tools/vita_app.py inspect paddle
.\.venv-devloop\Scripts\python.exe tools/vita_app.py check paddle
```

Edit `main.lua`, `PLAN.md` and the manifest's metric predicates to match the app.
The starter is a small paddle/ball simulation with an attract mode, bounds,
collision/score metrics and a reset path. The host validator compiles the actual
shared DevLoop Lua/core sources under sanitizers through the pinned offline Docker
image. It validates exact source bytes, bounded callbacks and declared behavior;
it does not contact a Vita.

Timing boundaries and deterministic controller traces can use the lower-level
checker. `CHECKS.json` contains a list of metric predicates; `INPUTS.json` contains
ordered frame events such as `[{"frame":10,"buttons":16384},{"frame":11,"buttons":0}]`
for a CROSS press/release. Values persist until changed; stick axes use 0..255.

```powershell
.\.venv-devloop\Scripts\python.exe -m app_tools.lua_check SOURCE.lua --checks CHECKS.json --frames 480 --dt 0.016666666666666666 --inputs INPUTS.json
```

For live iteration, obtain fresh `vita_workbench_prepare_script_session` output
using the exact installed DevLoop build. Save it privately and generate the
arguments without making a device call:

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py session-args paddle PREPARATION.json
```

Pass those arguments to `vita_workbench_script_session`. Never reuse old PID/run/
revision pins after another job or restart. Default restoration leaves the prior
scene paused. `--retain-best` requests a fresh paused VM of the selected source;
it does not preserve the measured simulation state. Lua scenes are not standalone
VPKs and have no script audio/files/texture API. [Lua contract](../SCRIPTING.md).

## Native project

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py new native-paddle --route native-slot --name "Native Paddle"
.\.venv-devloop\Scripts\python.exe tools/vita_app.py check native-paddle
.\.venv-devloop\Scripts\python.exe tools/vita_app.py build native-paddle --version 01.02
```

The project's `native-slot/` directory contains simulation, rendering and host
assertions. The wrapper supplies initialization, controller state, timing,
Vita2D drawing, authenticated status and graceful exit. Modify the app and its
assertions together. Application self-test contributes to the live
`selftest_passed` result; the existing CRC health vector stays separate.

Builds record all compiled envelope/module inputs, use the pinned SDK offline,
verify ARM/SELF authority, SFO/firmware and the fixed package layout, and publish
the candidate to `dist/native-lab`. Prior candidate/report files are retained
privately before replacement. No device files are changed by building.

Read Resident status, obtain a fresh `vita_workbench_native_preview` using the
package SHA, require `ready:true`, and execute that exact plan once. Acceptance
includes installed file hashes, exact native identity and independent inventory,
advancing frames, the app-inclusive self-test, graceful exit and observed absence.
A new source revision requires a new build and preview. On uncertainty, retain
the original job and use GET-only reconciliation without replay.

The fixed layout currently supports embedded assets only. Independent title IDs,
additional package paths, arbitrary VPKs and interrupted-operation recovery remain
separate work. The [native lifecycle guide](NATIVE-LIFECYCLE.md) retains operation,
capacity and conservative guard limits.

## Qualification

Skill syntax, project isolation, exact-byte session generation, shared Lua runtime,
native module assertions, ARM packaging and hardware execution are separate
evidence tiers. Current results are recorded in
[`make-vita-app-validation.json`](make-vita-app-validation.json). A planning forward
test and an implementation exercise are evaluated independently; a passing
template does not establish the correctness of future generated applications.

As of October 12, the project/skill host checks, actual shared Lua behavior tests
and isolated native ARM/package build passed. A plan-only music-player exercise
made no app/device changes. A breathing-timer scene passed its helper check and
13 supplementary cases; an incorrect-duration mutation was rejected.

Two Native Paddle builds then passed registered-MCP install/launch/evaluate/exit
cycles and GET-only reconciliation on the Vita. The second changed ball speed
from 220 to 300 pixels/second: the old position assertion failed as expected,
then the corrected behavioral expectation passed before version 01.03 was
redeployed. Both cycles verified installed hashes, native identity/inventory,
advancing frames, the app-inclusive self-test and graceful exit/absence. Each
took about 40 seconds. No FTP, Starter, reboot or manual installation was needed
after the physical wake. Physical controls, visual quality and prolonged use
remain separate checks; the previous five pristine Lab cycles remain separate
baseline evidence.

## Next: keep development jobs awake

The first preflight was unavailable because the Vita had slept, as the operator
later confirmed. A next qualification slice should provide a bounded Resident
work lease across active build/stage/run gaps, with expiry and explicit release
on completion, cancellation, faults or client loss. Ordinary sleep settings
should remain intact. This lease is not implemented or qualified by the app
workflow; true sleep can still require a physical wake.
