# Workbench release checklist

Use this sequence to turn the reviewed source candidate into a supported developer preview. Keep host, package, staging, device and physical results separate. Every device result must name the actual installed fingerprint and package hash. Current scoped results are in [qualification](QUALIFICATION.md); public candidate hashes are in [the build record](workbench-public-build-validation.json).

## Completed preparation

- [x] Import allowlisted Control 0.3.3 and Workbench sources without private pairing, device journals or unrelated apps.
- [x] Add the original ten Workbench tools to the existing background MCP and share the foreground session lock.
- [x] Check hash/revision guards, uncertain replies, ownership, paused restoration and invalid-version refusal through actual MCP fixtures.
- [x] Run C sanitizer harnesses, staging/retirement fixtures and native ARM/package validation in the isolated public checkout.
- [x] Record development-device input, power, synthetic filtering, Lua restoration and managed-file recovery separately from public packages.
- [x] Add portable host CI, setup guidance, qualification records and remaining gates.

## October 11 autonomous source candidate

- [x] Add the eleventh Workbench tool for one-attempt launch preparation with journaled observation and bounded power cleanup.
- [x] Freeze effective endpoints for preparation and trials; retain original endpoint cleanup after detected configuration drift.
- [x] Separate script readiness from native target/PID input readiness; block input-bearing profiles on legacy DevLoop before scene mutation and recheck before each input.
- [x] Add native DevLoop 01.04 title/PID, run and build telemetry, with PC runtime pinning and an exact caller build pin required for synthetic input.
- [x] Implement a separate default-disabled deferred one-shot startup helper with exact module hashes, consumed opt-in, retained duplicate-load guards, metadata probe and cancellation.
- [x] Retain the one-shot helper's native build and disabled staging record: seven files, two readbacks, active configuration and pairing preserved. [October 11 evidence](autonomous-candidate-validation.json).
- [x] Retain the complete final 17-group host pass, unchanged 221-file source/build snapshot, per-group log hashes and exact DevLoop 01.04 native build evidence in the [candidate record](autonomous-candidate-validation.json).
- [x] Verify a normal disabled boot through worker logs, expected Resident identity and Control absence.
- [ ] Verify one explicitly armed startup with exact external service identities and ordinary app operation. The first armed trial booted normally and submitted the exact native service, but Control work-power worker startup failed and its endpoint remained unavailable. Inspect and repair before another guarded attempt.
- [x] Build, stage with two readbacks and install exact DevLoop 01.04; verify stable native identity and the 55-step live Lua reload/recovery proof with original native scene restored paused.
- [ ] Qualify DevLoop 01.04 identity against fresh Control captures before re-enabling synthetic Workbench profiles on the test device. Control is unavailable after the first armed startup.
- [ ] Design and qualify persistent activation across repeated boots, duplicate detection, lifecycle recovery and failure handling. The one-shot helper does not satisfy this gate.

## 1. Finish the repaired development build acceptance

Use the exact matched pair selected for the current trial; the latest recorded pairing candidate is Control 0.3.4 / Starter 01.06. Control 0.3.3 observations below are history, not acceptance of the new pair. Load Starter only once after a confirmed normal boot, open native DevLoop paused and rest the Vita flat. Do not run Starter again or layer it over an uncertain automatic startup.

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
- [ ] Repeat power, synthetic exclusion, Target input/expiry/focus, script-only Lua, file recovery and completed capture checks with public build pins. Input-bearing Lua profiles additionally require installed native title/PID mapping and matched fresh captures.
- [ ] Repeat the physical gates above on the installed public pair.
- [ ] Qualify public DevLoop 01.04 title/PID/run/build telemetry, launch, Lua load/run/recovery, clean exit and sleep/return. Neither the older development 01.02 run nor the historical 01.03 build covers this candidate.

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
