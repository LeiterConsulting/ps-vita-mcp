# Isolated boot resource diagnostic 0.1.0

This experimental SceShell plugin diagnoses the first autonomous boot's generic
`work power worker failed` receipt. It does **not** load Control, its kernel
helper, any other plugin, or a network service. It cannot establish MCP readiness.
The proven Control pair and the failed one-shot Autostart candidate stay unchanged.

Control 0.3.4 succeeded when loaded by Starter into SceShell after boot. The same
pair failed during `rp_start` about 21.5 seconds into an autonomous boot.
That function collapses mutex creation, child-thread creation, and thread-start
errors to `-1`; current evidence does not identify which call failed or why.
Timing, wrapper resolution, and loader context remain hypotheses.

`module_start` creates and starts a worker at priority `0x40`, stack 32 KiB, and
returns immediately. It performs no file IO, AppMgr, networking, or Control calls
on the loader thread. The worker waits for at least 15 seconds of boot uptime and
three consecutive LiveArea (`NPXS10079`) observations, 500 ms apart. The gate
stops after 120 polls (at most 60 seconds of requested delays).

The only arm marker is `ux0:data/vita-boot-diagnostic/enable.once`, containing the
exact compiled lowercase 64-character source build ID, optionally followed by one
LF. `disabled`, `attempt.inflight`, or `enable.consumed` in that directory prevent
another attempt. Unknown file-state errors fail closed. An exclusive in-flight
guard is written, synced, and closed; the opt-in is renamed to `enable.consumed`
and the filesystem is synced **before** any resource trial. These records are
never removed by the plugin, including after a failed or unknown outcome.

The trial creates its own `boot-diag-power` mutex (attributes/count zero), creates
a no-op child at priority `0x60`, stack 32768, attributes/affinity zero, and starts
it. Those parameters and weak SceLibKernel wrapper imports match `rp_start`.
Every API return is logged separately in hexadecimal, alongside PID, thread ID,
boot time, build ID, and the addresses of the plugin's own import stubs. No pointer
is dereferenced for this diagnostic. Addresses alone do not prove resolution.

The child join has a five-second timeout. Only successfully owned resources are
deleted. An unconfirmed join or thread deletion retains the remaining resources;
there is no termination, reload, retry, or resource-name lookup. A `disabled`
marker is checked before the mutex, child creation, and child start. Cancellation
after the child starts still permits the bounded join and owned cleanup.
`module_stop` always cancels unload so code cannot disappear under a worker.
The immutable setup directory holds `startup.log`, capped at 8 KiB. Logging failure
cannot authorize a retry, but may leave the cause unobservable.

## Build and verify

The reproducible PC entry point is:

```powershell
.venv-devloop\Scripts\python.exe scripts/build_boot_diagnostic.py
```

It uses the project's pinned VitaSDK container, computes the source identity and
immutable setup path, runs host tests, verifies native metadata and imports, and
independently repeats ELF-to-VELF-to-compressed-SELF conversion with exact byte
comparison. The artifact hashes and build-bound module root are retained in
`dist/boot-diagnostic/build-report.json`. A successful native build remains
separate from physical boot acceptance, which has not been established for this
diagnostic.

For an independent SDK compilation using explicitly supplied identities:

```sh
cmake -S resident/boot_diagnostic -B build/resident/boot-diagnostic \
  -DDIAGNOSTIC_BUILD_ID=<exact-source-sha256> \
  -DDIAGNOSTIC_MODULE_ROOT=ux0:data/vita-boot-diagnostic/setup-<uuid>/
cmake --build build/resident/boot-diagnostic
sh resident/boot_diagnostic/test_host.sh
```

The staging operator uses that exact report, pins the active configuration bytes,
preserves rollback, and reads back the staged payload and opt-in before activation.
There is no automatic public staging script for this diagnostic.
The host test compiles the **actual adapter** against a fake SDK with strict
warnings, AddressSanitizer and UndefinedBehaviorSanitizer. It checks opt-in and
guard failures, minimum uptime/stable readiness/timeout, all resource API failure
paths, bounded cleanup, cancellation, log size, loader-thread isolation and
duplicate starts. This is offline qualification, not Vita API acceptance.

## Hardware trial and recovery

Keep existing consumed Autostart records intact. Stage this diagnostic in a new
immutable setup directory, read back its bytes, arm exactly this build, and add
only its new path to the active `*main` configuration beside the consumed helper.
Root tooling must pin the existing configuration bytes and preserve rollback.
Activate through a user-confirmed normal reboot; never hot-load it or rerun
Starter in the same boot to explain an unknown outcome.

After boot, collect the fixed setup's `startup.log`, the consumed marker, and the
in-flight guard through Resident or FTP. A positive mutex/thread trial only shows
that these parameters succeeded in this diagnostic's boot-worker context. It
does not prove the equivalent Control module or network startup will succeed.
Compare negative returns against the exact SDK/runtime before changing behavior.
If no log appears, check whether the diagnostic worker was submitted and whether
its fixed setup directory was writable; do not assume a specific API failed.

To prevent a future attempt, create `ux0:data/vita-boot-diagnostic/disabled` and
remove the diagnostic configuration line using the retained pre-change config,
then reboot normally. If a configuration change prevents normal startup, use the
previously qualified plugin-bypass boot procedure and restore that exact config.
Keep all attempt records until a human-confirmed fresh boot and an explicit new
trial; repeat-boot autonomy is not implemented by this diagnostic.
