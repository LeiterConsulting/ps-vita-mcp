# Removing routine FTP dependence

As of October 12, 2026, Resident already provides authenticated HTTP upload and
download to fresh, managed inboxes. Uploads verify streamed and stored SHA-256
hashes before publishing; the PC verifies two complete readbacks. Current leaves
are `package.vpk` and `probe.bin`, with an 8 MiB upload limit and a 64 KiB probe
limit. Lua sessions edit an open DevLoop directly and already require no FTP.

The next file-management service should extend Resident HTTP and the existing
MCP journals. Implementing a second FTP server would duplicate authentication,
attempt identities and transfer verification, while leaving installation and
app launching unresolved. This document is a plan, not implemented functionality.

## Work needed

1. Add bounded, paginated directory listing, stat/hash and read operations for
   managed project assets, logs and revisions. Control's existing workspace
   operations provide reusable behavior, but Resident must work independently
   of Control and Starter.
2. Add fresh revision writes and explicit hash-guarded cleanup. Confine routine
   operations to managed roots; give plugin/configuration updates their own
   narrowly scoped workflow with preserved rollback.
3. Expose transfer-job and retained-part inspection, free-space checks and quotas.
   Large assets need bounded resumable chunks, verified final assembly and
   reconciliation after interruption. Qualify native sync/recovery separately.
4. Implement package installation as a distinct journaled operation, binding
   package hash, title and build to installed/runtime verification and rollback.
   A successful upload is not an installed application.
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
- [Disabled native launch qualification candidate](RESIDENT-LAUNCH-CANDIDATE.md).

Services currently use unencrypted HTTP on a trusted LAN. This roadmap does not
make them suitable for exposure to the public internet.
