# Resident 0.1.3 native qualification candidate

As of October 12, 2026, the installed test Vita still runs Resident 0.1.2 and
DevLoop 01.04. The bounded Control-free Lua loop passed on that hardware. Resident
0.1.3 is a new build candidate. Immutable staging passed with two readbacks per
file and rollback preserved; it has not been activated or boot-tested.
Its [source and contracts](../resident/launch_broker/README.md) reuse Resident's
existing worker. Broker initialization never launches or loads another module;
ordinary Resident networking retains its existing network-module initialization.

The candidate adds a native random instance identity, strict administrator-only
broker routes, immutable attempt storage and read-only running-app inventory.
It keeps launching disabled in source. Even an accidental dispatch reaches an
unconditional refusal callback; no launch API is imported. The host adapter that
simulates a successful launch cannot compile into a Vita module. Its test markers
have no effect on the native candidate.

[Sanitized artifact, source, host-test and staging record](resident-launch-validation.json).

## Evidence and limits

The pinned SDK build checks the ARM module, exact source fingerprint, imports,
SELF metadata and unresolved symbols. Host tests exercise the actual Resident C
HTTP service, durable-record adapter on POSIX, strict JSON codec and portable core
under AddressSanitizer/UndefinedBehaviorSanitizer. They include incomplete replies,
failed socket closure, lost storage writes, restart, retained RNG failure and
continued ordinary Resident service after broker failure. Separate bounded-IO
tests inject partial writes, sync/readback failures and malformed record history.

These checks do not establish native boot, storage durability, SDK app inventory
semantics, displayed foreground, protected UI or successful app launching. Inventory
is deliberately labeled incomplete and non-atomic. The 128-record store never
prunes tombstones and accepts only its exact build/format; migration and production
retention still need an explicit design. A complete autonomous native development
loop remains unfinished.

## Deployment and hardware sequence

1. Preserve the working 0.1.2 plugin, exact active configuration, pairing and all
   experiment guards. Build 0.1.3 separately with `Build-Resident.ps1`.
2. Inspect the current device configuration and installed identity before staging.
   `resident/stage_update.py` can stage an immutable replacement plus rollback and
   a proposal that changes only the existing Resident path. It never activates it.
3. After a concrete staging receipt, copy that proposal and reboot normally once.
   Do not add a boot plugin, arm either withdrawn experiment or run Starter.
4. Verify normal boot and exact 0.1.3 build, stable native instance across repeated
   requests, advancing native time and `enabled:false`. Test ordinary status and
   verified inbox transfer independently. Preserve rollback on any failure.
5. Inspect app inventory in LiveArea and an open DevLoop; compare AppId/PID/title
   reports with known runtime identity. This comparison does not qualify focus.
6. Qualify native storage/sync/recovery separately, preserving every attempt. No
   offer/launch test is enabled by this candidate. A later reviewed adapter must
   implement an explicit foreground/protected-UI policy before native submission.

Human involvement is still needed for activation/reboot and physical acceptance.
After a launch adapter is qualified, the PC preparation tool can submit one
fixed-title attempt and then observe DevLoop's exact runtime. Native installation,
remote scene leases, keep-awake and asset delivery remain separate implementation
steps. Private iPhone implementation and raw device evidence remain outside the
public repository.
