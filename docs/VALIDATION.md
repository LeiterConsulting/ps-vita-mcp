# Validation and release criteria

The prototype has real-device evidence. The first imported public build was **01.03**; the October 11 source candidate is **01.04** with native process/build identity. Results from prototype 01.02 or public 01.03 do not certify changed code, packaging or setup.

## October 11 autonomous candidate

Development has resumed. The source adds one Workbench preparation tool, bringing the combined catalog to 28 tools (4 Resident + 13 Control + 11 Workbench), and an independent default-disabled one-shot startup helper. DevLoop 01.04 adds native title/PID, run and source-build identity; PC jobs pin that identity, and synthetic input requires an exact caller-supplied expected DevLoop build. [Autonomous scope](AUTONOMOUS-DEVLOOP.md) distinguishes healthy script runtime from verified native foreground input identity. Legacy installed DevLoop lacks title/PID telemetry, so synthetic Workbench profiles are blocked while script-only profiles remain available. Candidate identity and foreground mapping still require artifact-bound device acceptance.

The host CI runner is configured for 17 groups. It includes six native DevLoop identity regressions, preparation/endpoint decisions and real stdio MCP/local HTTP fixtures, the actual one-shot coordinator/probe/Vita adapter and separate boot resource diagnostic under SDK substitutes with sanitizers, and guarded startup staging fixtures. Its reports/logs establish the result of the exact checkout tested; host tests do not establish ARM build, installation, normal boot, network activation, physical input or repeated-boot acceptance. Build the experiment separately with `Build-Autostart.ps1` after matching Control artifacts and retain its own report. Hardware progression and remaining gates are in [the release checklist](RELEASE-CHECKLIST.md).

The [October 11 candidate record](autonomous-candidate-validation.json) records the helper's pinned-SDK native build and disabled staging: seven files, two readbacks each, active configuration and pairing unchanged, no active opt-in created. A normal disabled boot passed. The first armed trial booted normally and confirmed exact native submission, but Control's work-power worker failed and its network service was unavailable. DevLoop 01.04 passed its native build, staged with two readbacks, was installed and passed exact native runtime identity plus a 55-step live Lua reload/recovery proof with native scene restoration paused. Control capture mapping, synthetic input and lifecycle checks remain pending. The final 17-group host run passed, including endpoint consistency repairs and the separate boot resource diagnostic; all 221 selected source/build files were unchanged across that run. Its report and individual log hashes are retained in the candidate record. The diagnostic passed its pinned-SDK native build and 34 host adapter cases; its hardware trial is locally prepared and awaiting FTP, with no diagnostic staged or armed on the Vita.

The earlier dated JSON reports linked below remain historical records. They are not rewritten to certify the October 11 changes or a new device run.

## Existing evidence

As of October 2, 2026, development evidence includes:

- Host tests of native core, HTTP and Lua behavior under sanitizers.
- MCP stdio tests against explicit fixtures.
- ARM builds and VPK identity, metadata, artwork, archive and hash checks.
- Live command/status consistency checks on a physical Vita.
- Live Lua edit/run/capture/recovery and bounded workload/containment trials.
- File manager FTP transfer with two SHA-256 read-backs and manual installation.

Physical coverage is currently one homebrew-enabled Vita on firmware 3.65 with a Windows bridge. [Prototype results](prototype-validation.json) retain the exact 01.02 package hash and scoped live checks. [Screenshot provenance](screenshots.json) records hashes of the original captures; their local address is published with explicit permission. Pairing secrets and unrelated files are excluded.

## Original 01.03 public candidate changes

- Import only DevLoop and its supporting sources, examples, tests and pinned build inputs.
- Run the FTP fixture after building the VPK it consumes, so a fresh checkout works.
- Wait for graphics work and free the font before renderer teardown, then exit.
- Mark the app and package 01.03 and include the original-code MIT notice.

The graphics shutdown change follows the order used by the separately tested route probes, but **DevLoop 01.03 exit and sleep/return are still pending**. The [input manifest](prototype-source-manifest.json) records the imported prototype files before public adaptations; generated build reports record current source hashes.

## Imported checkout checks

The new checkout's isolated Python environment and full `Build-DevLoop.ps1` pass completed on October 2, 2026. [Build validation](build-validation.json) records the 01.03 VPK hash and scope:

- Native physics, core, actual HTTP-source and Lua harnesses passed under sanitizers, including 1,001 forced command/status pairs and a 6,000-frame Lua soak.
- Removing snapshot publication reproduced the expected stale-revision assertion, confirming the regression check detects that defect.
- MCP stdio bridge/script fixtures and six LiveArea image tests passed.
- The ARM app built and passed VPK archive, SFO, identity, firmware, artwork and hash checks.
- Thirteen FTP fixture groups passed, including corrupt/truncated transfers, rename faults, collisions and offline behavior.

These tests used host substitutes and local fixtures. They did not connect to, install on or alter the physical Vita. The locked Python dependencies emit an upstream `IncompleteFieldDefinitionWarning` during MCP startup; protocol fixtures passed, and the warning is retained in local logs.

## Background components added October 3, 2026

The public update adds Resident 0.1.1 and Inspector 01.03 as separate components. [Sanitized prototype results](resident-inspector-prototype-validation.json) record their exact native identities and scoped device observations. [Import manifest](resident-inspector-source-import.json) records source inputs before public-checkout adaptations.

- Resident answered background status and verified a 4 KiB probe and 1.2 MB package with the file manager in the foreground. Gameplay coexistence, sustained transfer load, app return and wake recovery remain open.
- Inspector 01.03 passed app and SceShell ABI/build/caller/permission/error checks. Both user proxies stopped/unloaded, and the app exited normally. The metadata-only kernel helper stays loaded until normal reboot.
- Control 0.2.0 boot activation hung and was rolled back. The later runtime-loaded Control 0.2.2 baseline below has its own scoped proof; Inspector metadata results alone do not establish its behavior.

Public adaptations remove dependence on private game packages and local artifact/config snapshots. Resident's native service retains four tools with DevLoop as its package registry entry; its combined desktop server now adds thirteen Control tools. Inspector and Starter retirement require the operator's inspected config hash, explicit normal-reboot confirmation and exact installed-package/guard identities. The public build does not install, activate, contact or test the Vita.

Git stores the native sources with LF line endings. Their source fingerprints and embedded build IDs therefore differ from the mixed-line-ending prototype, even where the normalized native source text matches. Public build hashes below describe the exact publication files; prototype hardware results remain bound to the prototype identities.

[Public-checkout build results](background-build-validation.json) report current native hashes and host checks. Their device-acceptance scope is separate from the archived prototype package and any future public installation.

## Functional MCP staging point added October 3, 2026

[The baseline](BASELINE.md) and its [machine-readable record](functional-mcp-baseline.json) bind the original Starter 01.00, Control 0.2.2, Resident 0.1.1 and DevLoop 01.02 identities to saved device evidence. That record includes matched readiness and normal Starter exit, actual registered MCP status, managed text/copy/hash-delete and one 1 MiB transfer, framebuffer readback, DevLoop launch/quit, five synthetic channels observed by Lua, expiry without PC release, stale-PID refusal and focus cancellation before deadline.

Warm preview/detail timings are individual samples; multi-second outliers occurred. Physical controller acceptance, sleep/wake, long sessions, unattended confirmation and native installation remain separate gates. At that October 3 staging point, the public DevLoop candidate was 01.03 and still needed its own hardware acceptance. These observations do not qualify the later 01.04 candidate.

Control publication adds source, runtime-only staging, explicit marker retirement, CLI diagnostics, loopback preview, documentation and support. Legacy boot activation is disabled. Fixtures test refusals before writes and uncertain rename behavior. Public sources are normalized to LF; their build fingerprints can differ from the recorded development artifacts. [Public baseline build results](public-baseline-build-validation.json) record current host/package qualification without claiming a new device run.

## First preview acceptance

| Gate | Required result |
| --- | --- |
| Clean checkout | Documented build and bridge setup work without development-machine paths or private configuration |
| Package | Unique app identity, correct metadata/artwork and recorded source/package hashes |
| Pairing | Fresh pairing works; missing/incorrect credentials and unavailable devices produce useful errors |
| Live loop | Both starter examples load, run, expose metrics and produce real-device screenshots |
| Recovery | Rejected edits preserve the current script; runtime faults pause; restart/rollback/native fallback work |
| Lifecycle | Release candidate exits cleanly and has explicitly tested sleep/return behavior |
| Transfer | Corruption is rejected, hashes bind the exact candidate and installation remains manual |
| Publication | Source, dependency notices, setup guide and validation summary describe the same release candidate |

A passed build is build evidence. A transferred VPK is transfer evidence. Graphics, audible audio, physical controls and recovery need the corresponding device observations.

## Workbench qualification on October 4 2026

[Current qualification](QUALIFICATION.md) separates the development Control 0.3.3 hardware run from fresh public package checks. The added host workflow runs portable C sanitizer harnesses, actual stdio MCP against local HTTP/FTP adapters and Workbench decision tests. It never connects to a Vita and does not certify native package installation, physical input or sleep/wake. Build-McpBaseline.ps1 additionally checks native ARM/package outputs in a fresh Windows checkout. [Release gates](RELEASE-CHECKLIST.md) define the remaining acceptance and publication sequence.
