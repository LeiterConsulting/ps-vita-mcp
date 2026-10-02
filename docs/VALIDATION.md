# Validation and release criteria

The prototype has real-device evidence, but the public source import will produce a fresh, independently identifiable release candidate. Results from the development workspace do not automatically certify changed packaging or setup instructions.

## Existing evidence

As of October 2, 2026, development evidence includes:

- Host tests of native core, HTTP and Lua behavior under sanitizers.
- MCP stdio tests against explicit fixtures.
- ARM builds and VPK identity, metadata, artwork, archive and hash checks.
- Live command/status consistency checks on a physical Vita.
- Live Lua edit/run/capture/recovery and bounded workload/containment trials.
- File manager FTP transfer with two SHA-256 read-backs and manual installation.

Physical coverage is currently one homebrew-enabled Vita on firmware 3.65 with a Windows bridge. Source import will include a concise sanitized evidence summary, with exact candidate hashes and test scope. Device addresses, pairing secrets and unrelated game files belong outside public evidence.

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
