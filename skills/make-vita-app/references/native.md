# Native development slot

Read `docs/NATIVE-LIFECYCLE.md` and `docs/MAKE-VITA-APP.md` in the resolved checkout. Resident accepts only `lifecycle_lab` / `VMCP00001`, eight fixed normalized files and the strict authenticated runtime envelope on port 17868. The pristine Lab remains the qualification baseline; `app_slot/` separately builds application modules into that explicitly replaceable development slot.

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py new paddle --route native-slot --name "Vita Paddle"
.\.venv-devloop\Scripts\python.exe tools/vita_app.py build paddle --version 01.02
```

Implement the module using the wrapper's real API. Keep simulation/assertions host-testable. The wrapper retains build/PID/run/revision status, known CRC vector and cooperative exit. Application self-test failure also makes `selftest_passed` false. Test actual app behavior; do not return unconditional success.

Inspect `app_slot/CMakeLists.txt` before choosing a native dependency. The current starter links Vita2D, controls, fonts, networking and kernel/thread support; it does not provide an audio player, media provisioning or arbitrary dependency declarations. Native audio or an existing engine may need reviewed build-adapter changes and a separate hardware slice.

The builder fingerprints compiled runtime/module inputs, runs host assertions, compiles through the pinned offline SDK, verifies SFO/SELF/package identity and publishes `dist/native-lab`. It retains the previous candidate/report privately. A build is not device acceptance. Embed assets for this slice; additional package paths need another supported adapter.

For authorized live work, identify the exact slot candidate/build/version and retained rollback, read Resident status, then call `vita_workbench_native_preview` with the package SHA. Require `ready:true`; execute its exact `plan` and `plan_sha256` once. Bounds: 1..3 same-candidate cycles, 0.25..10 seconds measurement, 10..180 seconds polling. Changed source needs a new preview.

Require successful promotion and installed hashes, exact runtime identity matched to independent inventory, advancing frames, app-inclusive self-test, graceful exit and observed absence. Save job ID/evidence. On uncertainty use `vita_workbench_native_reconcile(job_id)`; GET-only inspection cannot resume/replay. The guard does not attest every protected UI.

This is one prototype in a shared development bubble, not a separate product title. Preserve accepted apps and boot configuration. Control/startup experiments are unnecessary. Larger games, external assets, independent titles, interrupted-operation recovery and long unattended runs need further qualification. Respect 8 MiB/file, 16 MiB total and retained history bounds.
