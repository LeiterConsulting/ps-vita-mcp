# Native development slot

This backend builds a user-authored C prototype inside the one owned development
slot, `VMCP00001`. It preserves the qualified Lab protocol, authentication,
port17868, build marker and cooperative exit. It does not enable arbitrary title
installation. Each candidate replaces the earlier Lab or prototype in this slot;
the original `lifecycle_lab/` sources and tests stay unchanged.

Use the project helper through `make_vita_app`, or call the backend directly:

```powershell
.\.venv-devloop\Scripts\python.exe -m scripts.vita_native_slot scaffold .devloop-private/vita-apps/paddle/native-slot --name paddle --display-name "Vita Paddle"
.\.venv-devloop\Scripts\python.exe -m scripts.vita_native_slot inspect .devloop-private/vita-apps/paddle/native-slot
.\.venv-devloop\Scripts\python.exe -m scripts.vita_native_slot check .devloop-private/vita-apps/paddle/native-slot
.\.venv-devloop\Scripts\python.exe -m scripts.vita_native_slot build .devloop-private/vita-apps/paddle/native-slot --version 01.02
```

The Python API exports `scaffold(project_directory, name=..., display_name=...)`,
`inspect(project_directory)`, `check(project_directory)` and
`build(project_directory, version='01.02')`. Each accepts the repository `root`
keyword for host fixtures. Project paths must remain inside the repository and
may not traverse links. Scaffolding requires an absent leaf; existing parents
are allowed. Projects contain exactly `native-slot.json`, `app.c`, `app.h`,
`app_sim.c`, `app_sim.h` and `test_app.c`. Version1 supports this small module
layout and has no arbitrary dependency, asset or build-command declaration.

`app_api.h` declares native init, update, draw, self-test and cleanup callbacks.
Update returns nonzero only when current application state is healthy. A failed
update stops later application updates and permanently fails the live check for
that run, while the HTTP lifecycle service remains available for graceful exit.
The immutable wrapper owns the network service, native lifecycle identity, font
and presentation. Application code can use ordinary VitaSDK/vita2d APIs and owns
its resources. Native callbacks must return promptly; Lua instruction/memory
limits do not apply to C. `AppSlotInput` reports effective controller input;
there is no synthetic input in this backend. The demo uses a deterministic
paddle simulation whose host checks cover movement, walls, paddle collision,
miss/reset, bounded input, invalid time values and repeatability. Its native
`app_selftest()` runs the same pure simulation checks independently of gameplay.

The reused Lab CRC remains `0xa2912082`. The unchanged `selftest_passed` telemetry
combines the CRC, successful application initialization, application self-test
and the sticky health result from every application update.
The screen displays the application and CRC results separately. A failed
application self-test therefore follows the existing owned-runtime failure and
graceful cleanup path. The retained Lab `paused:true` field describes the
lifecycle envelope; prototype update/draw callbacks run independently. This is
not a general pause/resume application protocol.

Builds use the locked VitaSDK Docker image with networking disabled. Compiler
commands use argument arrays, not project-supplied shell text.
Commands have a 180-second limit (300 seconds for native compilation). A timeout
retains its log and removes only that command's uniquely named owned container;
failed cleanup is reported as unconfirmed.
All application, runtime, API, CMake, generated configuration, toolchain and builder inputs are
hashed into the exact native identity. A content-addressed immutable generated
header supplies the display label. The builder checks for source drift after
host verification, compilation and immediately before publication.

Actual compiler dependency output is checked against these declared pins.
Host `.d` files are inspected before running application simulation tests;
native Ninja dependency records are inspected before packaging/publication.
Both use isolated snapshots containing only declared hash-pinned repository
inputs; the original repository is never mounted into the compiler containers.
The native snapshot is fresh and excludes host-test-generated files. This also
prevents assembler `.incbin` or `.include` from reading undeclared files in the
original repository, since compiler dependency records do not list those reads.
An include outside the six project files, fixed framework or generated pinned
configuration is rejected instead of silently adopting an unreviewed repository
file. System and SDK headers belong to the digest-pinned offline toolchain image.
Reports retain the observed dependency list and verification result.

The seven-entry VPK remains compatible with the existing fixed Lab adapter.
An isolated source/package snapshot is checked by the unmodified candidate
validator before publishing `dist/native-lab/native_lab.vpk` and its report.
Previous candidates are retained under
`.devloop-private/native-slot-candidate-backups/`; publication failure restores
the previous directory. Build and sanitizer logs are under
`evidence/native-slot/`. The build report distinguishes host simulation,
native package, hardware lifecycle, application behavior and physical input.

A build performs no device requests. Use a fresh
`vita_workbench_native_preview` with the report's exact package SHA-256 and the
unchanged resulting plan for `vita_workbench_native_execute`. Existing ownership,
idle policy, journal, bounded cycles and unknown-effect/no-replay rules apply.
Neither successful compilation nor a Lab lifecycle pass proves physical input,
visual quality, sound or all application behavior.

Host checks: `python -m unittest app_slot.test_native_slot`. Template simulation
checks run under ASan/UBSan during both `check` and `build`.
`python -m app_slot.test_dependency_integration` runs separate explicit Docker
proofs that an undeclared host header blocks test execution, a header included
only by native `app.c` blocks publication, and native inline assembler cannot
embed an undeclared original repository file. Every failure preserves the prior
candidate byte-for-byte.
