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
