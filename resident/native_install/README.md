# Native installation service

This service admits explicit desktop administrator jobs for the registered
`lifecycle_lab` project, title `VMCP00001`. It does not run jobs at boot, modify
taiHEN configuration, uninstall applications, or replay interrupted operations.
The HTTP integration is in the parent Resident service; the public wire contract
and qualification status are documented in `docs/NATIVE-LIFECYCLE.md`.

## Storage and effect boundary

All paths are generated from fixed file indices and lowercase hexadecimal IDs.
The Vita adapter uses `ux0:data/vita-resident/n1/<Resident build ID>/`:

- `stages/<stage ID>/manifest.json` retains the exact request body and checksum.
- `stages/<stage ID>/package/` retains the eight independently hashed files.
- `attempts/<operation ID>/` retains a claim, dispatch intent and final receipt.

The exclusive, verified promotion working copy uses the separate short root
`ux0:data/vita-resident/p/<operation ID>/`. Every complete fixed file path,
including the longest LiveArea filename, remains below 128 bytes. This avoids
passing a near-limit directory to native code that appends child paths. The
promoter may consume this copy; the build-scoped original stage remains
available for inspection and later operations. No retained copy is reused or
removed automatically, including copies belonging to an older Resident build.

Records use an immutable payload plus SHA-256 checksum envelope, synced and read
back before success. The checksum detects corruption; administrator credentials
provide network authorization. A checksum is not a signature. Torn files remain
in place and their identifiers cannot be reused. This first slice retains all
stages and attempts and applies fixed count and free-space limits.

An accepted operation first returns a durable queued receipt. Dispatch occurs
only after Resident confirms the response was completely sent and its socket
closed. A complete, synced intent precedes the one native submission. Candidate
hashes, SFO identity, unsafe SELF identity and the full native build marker are
checked before admission and again before dispatch. Only an absent target or an
installed target matching an earlier strictly validated `installed_verified`
receipt is eligible for installation.

The Vita adapter requires an already loaded PAF and an unloaded PromoterUtil.
It owns only the PromoterUtil module it explicitly loads for the operation.
Immediately after initialization it repeats the idle and time guards before
calling the asynchronous promoter. It checks both polling API results and the
reported operation result, then verifies every installed file. Uncertain
submission, polling, cleanup, storage or restart state blocks further mutations.
Recovery inspects durable evidence and never dispatches work.

`installed_verified: true` belongs only to a successful native installation
receipt. A launch receipt reports submission separately and does not claim the
application is running or ready. Native inventory and the lab's authenticated
runtime report provide those later observations.

## Verification

Run `sh resident/native_install/test_host.sh` in the pinned build image. The C
harness uses real POSIX files, exclusive writes, no-follow path walks, sync,
checksummed journals, streaming and readback, with simulated Vita SDK effects.
It covers install/launch/reinstall and restart, a consumed promoter working
copy, malformed requests, partial uploads, unknown installed titles, symlinks,
storage failure, SDK submission/poll/result/cleanup faults, installed-byte
corruption, timeout, late policy refusal and forged checksummed receipt binding.

Passing host tests and compiling the Vita adapter do not qualify hardware
installation. Promoter availability, the independently generated package
header, preservation of the installed fixed files, actual launch and runtime
readiness each require separate device evidence.
