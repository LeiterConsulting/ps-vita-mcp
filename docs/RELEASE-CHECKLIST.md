# Workbench release checklist

Use this sequence to turn the reviewed source candidate into a supported developer preview. Keep host, package, staging, device and physical results separate. Every device result must name the actual installed fingerprint and package hash. Current scoped results are in [qualification](QUALIFICATION.md); public candidate hashes are in [the build record](workbench-public-build-validation.json).

## Completed preparation

- [x] Import allowlisted Control 0.3.3 and Workbench sources without private pairing, device journals or unrelated apps.
- [x] Add ten Workbench tools to the existing background MCP and share the foreground session lock.
- [x] Check hash/revision guards, uncertain replies, ownership, paused restoration and invalid-version refusal through actual MCP fixtures.
- [x] Run C sanitizer harnesses, staging/retirement fixtures and native ARM/package validation in the isolated public checkout.
- [x] Record development-device input, power, synthetic filtering, Lua restoration and managed-file recovery separately from public packages.
- [x] Add portable host CI, setup guidance, qualification records and remaining gates.

## 1. Finish the repaired development build acceptance

With the existing matched Control 0.3.3 pair already loaded, open native DevLoop paused and rest the Vita flat. Do not run Starter again in the same boot.

- [ ] After a fresh dim cycle, hold only the bottom edge of the front panel for eight seconds. Require foreground contact telemetry, visible brightening, brightness throughout the hold, neutral release and a subsequent dim cycle.
- [ ] Repeat for the rear panel, avoiding the front panel, buttons and sticks.
- [ ] Repeat isolated D-pad LEFT, left stick, right stick and motion-only gestures on this exact fingerprint. Confirm visible restoration as well as telemetry.
- [ ] Complete a bounded capture soak with a final result and power cleanup receipt. Retain the incomplete October 4 run as a separate attempt.
- [ ] Manually sleep for at least 45 seconds, wake and prove unchanged module identity, fresh capture/input, no stale lease and usable foreground state without reload.
- [ ] Disconnect Wi-Fi externally while the Vita remains still. Stop PC renewals and reconnect before the last accepted 30-second work lease expires; require restored brightness and cleared work/dimming independently of expiry or physical activity.

Run the observers described in [Workbench](../workbench/README.md). Store raw evidence privately. A mixed gesture, stale sample or missing visual observation is unresolved and must not become a pass.

## 2. Qualify the public artifacts

- [ ] Build the reviewed commit using `Build-McpBaseline.ps1`, retaining all component reports, source hashes and VPK hashes.
- [ ] Stage exact candidates with two readbacks. Keep the old packages, active tai configuration and pairing for rollback. Installation, normal reboot and activation remain manual.
- [ ] Inspect installed Starter and Target entries against their public reports. Retire an old guard only after a confirmed normal reboot, Control absence and exact inspected identities. Never remove an active guard or load Starter twice per boot.
- [ ] Prove the public Resident identity after its deliberate installation, then the matched public Control ABI/build through actual desktop MCP.
- [ ] Repeat power, synthetic exclusion, Target input/expiry/focus, both Lua profiles, file recovery and completed capture checks with public build pins.
- [ ] Repeat the physical gates above on the installed public pair.
- [ ] Qualify public DevLoop 01.03 launch, Lua load/run/recovery, clean exit and sleep/return. The older development 01.02 run does not cover the changed shutdown code.

The [setup guide](GETTING-STARTED.md) preserves storage/plugin settings and describes rollback. A staged inbox or native launch receipt alone does not prove installation or runtime.

## 3. Reproduce setup and finish notices

- [ ] Reproduce setup from a clean Windows machine with a second operator, fresh tokens and the documented tools. Do not rely on development-machine paths, caches or configuration.
- [ ] Check missing/wrong credentials, offline errors, MCP restart, reboot/guard recovery and unknown file outcomes using the user-facing guide.
- [ ] Audit every linked SDK library and include required license texts in each distributed package and release bundle. Source notices and original-code MIT files are present; the complete binary notice audit remains open.
- [ ] Add another Vita/storage/plugin configuration, or explicitly scope the preview to the single tested configuration.
- [ ] Measure longer work sessions and capture overhead. Exercise larger transfers before claiming the full 8 MiB limit as qualified.

## 4. Publish the developer preview

- [ ] Require passing CI on the reviewed commit and review the source diff, privacy exclusions and dependency notices.
- [ ] Publish a versioned source tag only after review. Attach binaries only after the package and notice gates above pass.
- [ ] Include checksums, exact component versions/fingerprints, setup/rollback instructions and a sanitized device acceptance record bound to those artifacts.
- [ ] Keep known limits in the release notes: trusted LAN HTTP, on-demand screenshots with outliers, bounded synthetic input, foreground Lua, manual native installation and no forced wake.

After preview acceptance, prioritize resumable job receipts and recovery after host interruption, measured capture improvements, and a small Lua asset/audio interface. Expand capabilities with separate measurable trials rather than treating a successful heartbeat as a complete autonomous session.
