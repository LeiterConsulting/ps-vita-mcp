# Contributing

The repository includes DevLoop, the background Resident service, read-only Inspector, desktop bridges, examples and tests. DevLoop candidate 01.03 is under qualification; its screenshots describe prototype 01.02. Resident and Inspector have separate scoped hardware results and build instructions.

Useful early contributions include questions about setup, small original experiment ideas, additional device/host test coverage and focused design feedback. Open an issue with the workflow you want to improve and a concrete example.

## Reporting a problem

Include the app/bridge version, package hash when available, Vita firmware/model, host OS, reproduction steps, expected behavior and actual behavior. State whether the result came from a host test, package validation or physical device use.

Share a minimal script and sanitized error output. Remove pairing tokens, credentials, private addresses and unrelated files before posting. Game data is supplied separately; do not attach proprietary game assets to issues or pull requests.

## Proposing a change

Keep changes small and describe the resulting behavior. Include validation appropriate to the changed component and identify physical checks that still need a device. Reuse the current recovery behavior when adding capabilities. Follow [the setup guide](docs/SETUP.md) and run `Build-DevLoop.ps1` for native/protocol changes. Tests use host and local network fixtures; they do not contact your Vita.

Run `Build-Resident.ps1` for Resident changes and `Build-Inspector.ps1` for Inspector changes. Their default tests use host adapters and local fixtures without contacting the Vita. Live proofs, FTP staging, configuration activation and session retirement are explicit device operations; coordinate them separately from a source review.

Original contributions use the project's MIT license. Imported dependencies retain their own notices and licenses.
