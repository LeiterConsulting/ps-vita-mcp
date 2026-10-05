# Contributing

The repository includes DevLoop, the background Resident and Control services, runtime Starter, read-only Inspector, desktop bridges, examples and tests. Start with the [functional MCP baseline](docs/BASELINE.md) and [complete setup guide](docs/GETTING-STARTED.md). DevLoop candidate 01.03 still needs physical qualification; recorded runtime evidence uses 01.02. Fresh public builds and their hardware acceptance are separate results.

Useful early contributions include questions about setup, small original experiment ideas, additional device/host test coverage and focused design feedback. Open an issue with the workflow you want to improve and a concrete example.

## Reporting a problem

Include the app/bridge version, package hash when available, Vita firmware/model, host OS, reproduction steps, expected behavior and actual behavior. State whether the result came from a host test, package validation or physical device use.

Share a minimal script and sanitized error output. Remove pairing tokens, credentials, private addresses and unrelated files before posting. Game data is supplied separately; do not attach proprietary game assets to issues or pull requests.

## Proposing a change

Keep changes small and describe the resulting behavior. Include validation appropriate to the changed component and identify physical checks that still need a device. Reuse the current recovery behavior when adding capabilities. Follow [the setup guide](docs/SETUP.md) and run `Build-DevLoop.ps1` for native/protocol changes. Tests use host and local network fixtures; they do not contact your Vita.

Run `Build-Resident.ps1` for Resident changes, `Build-Control.ps1` for Control/Starter changes, and `Build-Inspector.ps1` for Inspector changes. `Build-McpBaseline.ps1` runs the three baseline component builds sequentially; `-IncludeInspector` adds the optional diagnostic. Their default tests use host adapters and local fixtures without contacting the Vita. Live proofs, FTP staging, configuration activation and session retirement are explicit device operations; coordinate them separately from a source review.

Original contributions use the project's MIT license. Imported dependencies retain their own notices and licenses.

## Public source and private phone app

This repository publishes the PC bridges, Vita services, Workbench, examples, tests and public guides. The iPhone Companion implementation remains private. Do not add its Swift packages, Xcode projects, signing material, app builds or handoff archives. Phone documentation belongs in `docs/`; the public [Companion guide](docs/IPHONE-COMPANION.md) describes the workflow and protocol without distributing the app.

Run `python scripts/check_public_scope.py` before publishing. CI repeats this tracked-path check; it also catches files force-added despite `.gitignore`. Keep credentials and device evidence excluded, and inspect the diff for private content before pushing. Passing this filename check does not establish that arbitrary file contents are safe to publish.
