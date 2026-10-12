# Removing routine FTP dependence

As of October 12, 2026, Resident already provides authenticated HTTP upload and
download to fresh, managed inboxes. Uploads verify streamed and stored SHA-256
hashes before publishing; the PC verifies two complete readbacks. Current leaves
are `package.vpk` and `probe.bin`, with an 8 MiB upload limit and a 64 KiB probe
limit. Lua sessions edit an open DevLoop directly and already require no FTP.

The next file-management service should extend Resident HTTP and the existing
MCP journals. Implementing a second FTP server would duplicate authentication,
attempt identities and transfer verification, while general installation and
app-launch support would still require separate qualification. The first read-only inbox slice was qualified in
Resident 0.1.4: [managed inbox inspection](MANAGED-FILES.md). Initial normal boot,
known-byte listing/hash/read and refusal checks passed. A separate DevLoop
coexistence check also passed, including a new 4096-byte upload, two complete
publication readbacks and exact managed stat/readback. The broker remained
disabled and unblocked. Repeated boot, storage durability and phone credential
confirmation remain unqualified. The Resident 0.1.5 [native lifecycle candidate](NATIVE-LIFECYCLE.md) now implements normalized package staging, native promotion and fixed-title launching for the owned Lifecycle Lab, with four native Lab cycles across two builds passed and same-build journal durability after reboot pending. The corrected 0.1.5 is now boot-loaded and exact-binary verified under a fresh unblocked, installer-ready native instance, with Promoter unloaded; four fixed-Lab install/launch/evaluate/graceful-exit cycles across two native builds passed on hardware; same-build journal durability after reboot remains pending. The earlier unknown receipt is retained without replay. [Current incident](NATIVE-LIFECYCLE.md#october-12-native-promotion-incident). The remaining work below extends or qualifies those bounded capabilities.

## Work needed

1. Extend bounded listing, stat/hash and reads beyond the implemented inbox and
   retained-part inspection to managed project assets, logs and revisions. Control's existing workspace
   operations provide reusable behavior, but Resident must work independently
   of Control and Starter.
2. Add fresh revision writes and explicit hash-guarded cleanup. Confine routine
   operations to managed roots; give plugin/configuration updates their own
   narrowly scoped workflow with preserved rollback.
3. Add durable transfer-job metadata, free-space checks and quotas alongside the
   implemented observational retained-part inspection. Large assets need bounded
   resumable chunks, verified final assembly and reconciliation after interruption.
   Qualify native sync/recovery separately.
4. Qualify the implemented Resident 0.1.5 journaled installation and lifecycle
   adapter on the fixed Lifecycle Lab title, then extend it deliberately to
   DevLoop and other owned projects. Bind package hash, title and build to
   installed/runtime verification; rollback and ownership migration need their
   own workflows. A successful upload is not an installed application.
5. Replace FTP-based Resident update staging with a dedicated update/proposal
   endpoint. Preserve the working plugin, pairing and exact prior configuration;
   activation and reboot need their own qualification.

File access, installation and launching should each report their own receipts.
An uncertain response must lead to inspection of the original attempt rather
than automatic replay. Keep an external FTP or USB recovery route for occasions
when Resident itself cannot start. The target is daily development through MCP
without opening a third-party file manager.

## Existing source

- [Resident transfer service](../resident/service.c) and [PC MCP bridge](../resident/bridge.py).
- [Control managed workspace HTTP](../resident/control/http.c) and
  [native filesystem adapter](../resident/control/platform_shell.c).
- [Current FTP-based update staging](../resident/stage_update.py).
- [Native Lifecycle Lab candidate](NATIVE-LIFECYCLE.md) and the separate
  [disabled legacy DevLoop launch broker](RESIDENT-LAUNCH-CANDIDATE.md).

Services currently use unencrypted HTTP on a trusted LAN. This roadmap does not
make them suitable for exposure to the public internet.
