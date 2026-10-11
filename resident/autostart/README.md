# Experimental one-shot automatic startup

This independent SceShell plugin tests delayed, automatic loading of the existing matched Control kernel/service pair. It is **not qualified on hardware**, does not replace Resident, and does not implement persistent startup across multiple boots. Resident and Control source fingerprints are unchanged by this experiment.

`module_start` only creates/starts its worker and returns. The worker waits for at least 15 seconds of system uptime and three consecutive, half-second AppMgr observations of LiveArea's companion process (`NPXS10079`). A 120-second deadline ends the attempt without loading anything. This process signal follows [AutoBoot's existing approach](https://github.com/Rinnegatamante/AutoBoot/blob/master/main.c); its suitability for this Vita's firmware remains a hardware gate.

The experiment is disabled unless `ux0:data/vita-autostart/enable.once` contains exactly the 64-character expected Control build ID, with an optional LF. The `disabled` marker inhibits startup and cancels pending work. Storage errors fail closed.

Before loading anything, the worker refuses an existing `attempt.inflight`, `enable.consumed`, or `ux0:data/vita-control/control-session.lock`. It creates an exclusive in-flight guard, renames `enable.once` to `enable.consumed`, syncs storage, and creates the normal Starter guard. It never deletes these markers. A normal reboot and inspected guard retirement are required before another experiment; a missing endpoint is not permission to repeat a load.

It verifies SHA-256 of all three immutable native files, submits the kernel once, loads its own temporary probe, validates exact kernel ABI/build/readiness and `caller == Shell`, releases only that temporary probe, then submits Control into its own SceShell process once. Cancellation after the kernel retains the kernel until reboot. Cancellation after probe submission releases the temporary probe and suppresses service submission. It never unloads/reloads Control or its kernel.

`ux0:data/vita-autostart/startup.log` is bounded to 8 KiB and retains timestamps, stage names and raw loader/IO results. The unique report directory contains bootstrap metadata. These files contain no pairing codes or credentials. The final successful state is **modules submitted; network unverified**. An external exact-identity status read is still required.

Build this directory independently using the repository's pinned VitaSDK image. Required CMake arguments:

| Argument | Meaning |
| --- | --- |
| `CONTROL_BUILD_ID` | Exact existing Control source fingerprint |
| `CONTROL_KERNEL_SHA256` | Exact kernel SELF bytes |
| `CONTROL_SERVICE_SHA256` | Exact service SELF bytes |
| `CONTROL_STUB_DIR` | Directory containing matched `libvita_control_kernel_stub.a` |
| `CONTROL_MODULE_ROOT` | Fixed `ux0:data/vita-autostart/setup-<hex-or-hyphens>/` directory |

The probe SELF is built first; its actual hash is generated into `probe_hash.h` for the plugin. Both modules are unsafe user plugins, not kernel boot entries. This directory's CMake does not modify or rebuild the existing Control pair.

Run portable tests from the checkout root:

```sh
sh resident/autostart/test_host.sh
```

The tests compile the actual coordinator, Shell probe and Vita adapter against simulated SDK calls, with address/undefined-behavior sanitizers. They exercise loader-thread isolation, readiness/deadlines, guard races, consumption/write/sync failures, all three file hashes, metadata rejection, late disable markers and bounded one-attempt behavior. Passing host tests is not native startup acceptance.

Hardware progression: inspect current configuration and native identities; preserve rollback; confirm a normal reboot; inspect/retire the prior guard; stage the immutable setup with startup disabled; verify a normal boot; arm one controlled startup; verify Resident and Control exact identities externally; inspect logs and ordinary app operation. Persistent activation, duplicate-kernel detection, sleep/wake and repeated-boot qualification remain later work.
