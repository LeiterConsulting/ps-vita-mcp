# Disabled Resident launch broker qualification

As of October 12, 2026, Resident 0.1.4 is installed alongside DevLoop 01.04 on the
test Vita, with 0.1.3 and 0.1.2 retained for rollback. Its [current managed-file
qualification](managed-files-validation.json) includes normal boot, exact
configuration/plugin, inbox inspection and bounded DevLoop coexistence with a
fresh 4 KiB upload and verified readbacks. Launching remains disabled and refused.

The following records the earlier 0.1.3 native qualification. The operator
confirmed normal boot after its activation. Read-only checks
matched the proposed configuration and exact plugin, preserved the 0.1.2 rollback
and saved administrator pairing, and verified no configuration override and both
withdrawn experiments disabled. Immutable staging had passed with two readbacks
per file. The bounded Control-free Lua loop's earlier hardware proof is separate.
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
[October 12 physical-device qualification and Lua regression](resident013-device-validation.json).

Three historical 0.1.3 live broker samples matched the exact candidate build, retained one native
instance and advanced native time. `enabled`, `configured_enabled` and `blocked`
were all false. Initial inventory reported one resolved file-manager entry with
AppId/PID/title; foreground, protected-UI and native-submission flags stayed false.
Fresh stdio MCP status and a 4 KiB probe with two complete readbacks passed.
With DevLoop open and paused, eight additional read-only observations retained
its exact native build/PID/run and revision while frames advanced; inventory's
`CHRS00003` PID matched every sample. Resident retained its native instance and
advanced its clock with the broker disabled and unblocked. A separate fresh
stdio MCP status/probe proof passed in that state with the same Resident start
time as the file-manager proof. These observations changed no scene, and no foreground or
protected-UI attestation was established.
The bounded two-candidate Lua proof subsequently passed with 0.1.3 running in
the background: rates 60/120, faster candidate selected, original native
world/mode/parameters/ball/score/obstacles restored paused, and exact DevLoop
build/PID/run retained. Lua finished inactive with the last VM retained, the
documented native-fallback limit. The broker retained its instance and stayed
disabled and unblocked.
The registered desktop connection remains an older 28-tool process and needs refreshing from the updated PC source. Fresh stdio verified the historical 30-tool 0.1.3 catalog and now verifies all 33 tools with installed 0.1.4. Desktop discovery does not qualify native launching.

## Evidence and limits

The pinned SDK build checks the ARM module, exact source fingerprint, imports,
SELF metadata and unresolved symbols. Host tests exercise the actual Resident C
HTTP service, durable-record adapter on POSIX, strict JSON codec and portable core
under AddressSanitizer/UndefinedBehaviorSanitizer. They include incomplete replies,
failed socket closure, lost storage writes, restart, retained RNG failure and
continued ordinary Resident service after broker failure. Separate bounded-IO
tests inject partial writes, sync/readback failures and malformed record history.

The initial normal boot, identity/clock, file-manager inventory, DevLoop PID
correlation, HTTP transfer and bounded Lua coexistence checks passed. They do not
establish storage durability across reboot, displayed foreground, protected UI or
successful app launching.
Phone credential confirmation remains pending. Inventory is deliberately labeled
incomplete and non-atomic. The 128-record store never
prunes tombstones and accepts only its exact build/format; migration and production
retention still need an explicit design. A complete autonomous native development
loop remains unfinished.

## Historical 0.1.3 deployment and remaining hardware gates

This sequence records the completed 0.1.3 activation, not instructions to replace
installed 0.1.4. Current source builds 0.1.4; preserve both rollback plugins and
follow the [current Resident update guide](RESIDENT.md) for any new replacement.

1. Preserve the working 0.1.2 plugin, exact active configuration, pairing and all
   experiment guards. Build 0.1.3 separately with `Build-Resident.ps1`.
2. Inspect the current device configuration and installed identity before staging.
   `resident/stage_update.py` can stage an immutable replacement plus rollback and
   a proposal that changes only the existing Resident path. It never activates it.
3. After a concrete staging receipt, copy that proposal and reboot normally once.
   Do not add a boot plugin, arm either withdrawn experiment or run Starter.
4. Initial gate passed on the test Vita: normal boot, exact 0.1.3 build, three
   stable-instance/advancing-clock samples, disabled broker, ordinary status and
   a 4 KiB probe with two readbacks. Repeated boots and storage durability remain
   separate gates. Preserve rollback on any failure.
5. Initial file-manager inventory and eight DevLoop PID-correlation samples
   passed. LiveArea and protected-UI comparisons remain pending. Inventory
   correlation cannot qualify displayed foreground or focus.
6. Qualify native storage/sync/recovery separately, preserving every attempt. No
   offer/launch test is enabled by this candidate. A later reviewed adapter must
   implement an explicit foreground/protected-UI policy before native submission.

Human involvement is still needed for activation/reboot and physical acceptance.
After a launch adapter is qualified, the PC preparation tool can submit one
fixed-title attempt and then observe DevLoop's exact runtime. Native installation,
remote scene leases, keep-awake and asset delivery remain separate implementation
steps. Private iPhone implementation and raw device evidence remain outside the
public repository.
