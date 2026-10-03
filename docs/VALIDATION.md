# Validation and release criteria

The prototype has real-device evidence. The imported public source builds a fresh, independently identifiable **01.03** candidate. Results from prototype 01.02 do not certify changed code, packaging or setup.

## Existing evidence

As of October 2, 2026, development evidence includes:

- Host tests of native core, HTTP and Lua behavior under sanitizers.
- MCP stdio tests against explicit fixtures.
- ARM builds and VPK identity, metadata, artwork, archive and hash checks.
- Live command/status consistency checks on a physical Vita.
- Live Lua edit/run/capture/recovery and bounded workload/containment trials.
- File manager FTP transfer with two SHA-256 read-backs and manual installation.

Physical coverage is currently one homebrew-enabled Vita on firmware 3.65 with a Windows bridge. [Prototype results](prototype-validation.json) retain the exact 01.02 package hash and scoped live checks. [Screenshot provenance](screenshots.json) records hashes of the original captures; their local address is published with explicit permission. Pairing secrets and unrelated files are excluded.

## Public candidate changes

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
- Control 0.2.0 boot activation hung and was rolled back. These metadata results do not establish cross-app input, screen capture, broader Control stability or automatic installation.

Public adaptations remove dependence on private game packages and local artifact/config snapshots. Resident publishes four tools with DevLoop as its package registry entry. Inspector retirement requires the operator's inspected config hash, explicit normal-reboot confirmation and exact installed-package/guard identities. The public build does not install, activate, contact or test the Vita.

Git stores the native sources with LF line endings. Their source fingerprints and embedded build IDs therefore differ from the mixed-line-ending prototype, even where the normalized native source text matches. Public build hashes below describe the exact publication files; prototype hardware results remain bound to the prototype identities.

[Public-checkout build results](background-build-validation.json) report current native hashes and host checks. Their device-acceptance scope is separate from the archived prototype package and any future public installation.

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
