# Functional MCP staging point — October 3, 2026

This baseline is the minimum operational prerequisite for subsequent autonomous DevLoop work. It combines the foreground Lua host with a background status/file service and a runtime-loaded Control pair. The immutable source tag is **`functional-mcp-2026-10-03`**. [Machine-readable identities and criteria](functional-mcp-baseline.json), [public host-build results](public-baseline-build-validation.json).

## Recorded runtime

| Component | Version | Role |
| --- | --- | --- |
| Vita DevLoop, `CHRS00003` | 01.02 | Foreground Lua edit/run/observe/recover |
| Vita Resident | 0.1.1 | Boot-loaded background status and verified package inbox |
| Control service / kernel | 0.2.2, ABI 1 | Background screen, files and bounded injected input |
| Control Starter, `CHRS00011` | 01.00 | Explicit one-load activation after a normal boot |
| Control Inspector, `CHRS00010` | 01.03 | Optional read-only diagnostic; not required for normal use |

The physical record covers one modded firmware-3.65 Vita and a Windows bridge. The public DevLoop 01.03 candidate changes shutdown and version reporting; it must pass its own installation, live-loop and lifecycle checks. Control/Resident source fingerprints and package identities are tracked separately. New builds, different firmware, plugins, storage layouts or models need fresh qualification.

## Demonstrated capabilities

| Capability | Recorded result and limit |
| --- | --- |
| Runtime activation | Exact installed Starter/helper/SFO hashes; matched readiness metadata; Shell service listening; Starter exited normally |
| Background MCP status | Actual registered client answered after PC bridge restart, while the file manager was foreground |
| Managed files | Text publish plus two readbacks, direct read/stat/hash, copy/list, wrong-hash delete refusal, matching-hash delete; original probe retained |
| Larger WiFi transfer | One 1 MiB file uploaded in 1.947 s, then completely read back twice in 1.854 s and 0.705 s |
| Screen readback | Observed file manager, LiveArea and DevLoop; preview 240×136, detail 480×272 |
| DevLoop app control | Launch confirmed by its display and live telemetry; quit confirmed by return to Shell display |
| Injected input | Right+cross, both stick offsets, and exact front/rear contacts observed by DevLoop; calibrated monitor latched all five channels over 46 frames |
| Automatic input expiry | No PC release sent; app saw buttons/sticks/contacts return to normal and Control lease became zero |
| Stale target guard | Previous Shell PID rejected with HTTP 409 while DevLoop displayed; no active lease afterward |
| Focus cancellation | One-second neutral lease cleared 482 ms after submission when DevLoop was closed; subsequent display was Shell |
| Live development loop | Hash-verified Lua upload, paused preflight, resume, input trial, app metrics and screen readback |

The first launch's Shell-confirmation touch was interrupted by the user. It does not qualify unattended confirmation handling. Launch was repeated only after the user requested it.

## Important limits

- **Latency varies.** Two warm previews with the file manager foreground measured 126/132 ms and detail 324 ms; other captures took multiple seconds, including 11.45 s during DevLoop launch. Native pixel copying measured roughly 14–33 ms in these samples. This is usable on-demand interaction, with no sustained video/FPS or latency guarantee. A copy may span rendered frames.
- **Stick emulation adds to physical centers.** Request `[32,224]` on a left stick centered near `[135,125]` read about `[39,221]`. The monitor calibrates the baseline with a three-byte tolerance. Input receipt acceptance does not prove an exact absolute stick position.
- **Input is bounded.** One touch point per panel, normal game buttons and both sticks; 16–1000 ms leases. PS, power and volume are excluded. Effective input includes physical and synthetic contributions. This proof does not substitute for human controller acceptance.
- **Files are scoped.** Control manages fresh revisions under `ux0:data/vita-control/workspace`, up to 8 MiB. It does not write system files or installed app trees. Local publication is restricted to this checkout's `outgoing/` directory.
- **Activation and installation are manual.** Control starts through Starter after boot. VPK upload does not install/activate a package. Reboot removes runtime modules and requires inspected marker retirement before another load.
- **Sleep/long runs remain open.** No keep-awake behavior is installed. True sleep or WiFi loss can make services unavailable. Sustained captures, long gameplay coexistence, wake recovery, reconnection under faults, and additional device combinations remain unqualified.
- The public project ships no Quake/game data. Native `CHRS00009` app commands are retained from the experiment allowlist but are optional; DevLoop is the required baseline target.

## Acceptance on a new device

Use [GETTING-STARTED.md](GETTING-STARTED.md), then retain evidence for each of these gates:

1. Host builds and fixture tests pass; record commit, component fingerprints and package hashes.
2. Normal boot succeeds with the intended Resident configuration; exact Resident status responds.
3. Starter installs, loads the matched pair once, and exits normally; Control responds after exit without a boot config entry.
4. Correct foreground images and advancing frame metadata are observed; status/file service survives an app switch.
5. A fresh managed file passes full readback/hash checks, with no automatic publication replay.
6. DevLoop launches and responds; a known Lua candidate is hash-verified, preflighted and observed.
7. Each requested input channel is observed in app telemetry, expires without a PC release, and leaves normal input afterward.
8. A stale PID is refused; focus change cancels a live neutral lease before its deadline.
9. Restore settings, pause the experiment, and retain source/receipts/images and any open limitations.

Future autonomous work must check these gates for its current device/session rather than assuming that a historical build or online heartbeat proves them. Sleep, unattended installation and long-run reliability require additional explicit acceptance.

## Next work built on this staging point

The first autonomous slice should observe the current target/build, submit a fresh Lua revision, validate its hash, run a bounded trial, collect app metrics and images, compare explicit criteria, and retain or roll back the candidate. Timed-out writes/actions require readback before any decision. Durable projects, improved latency, calibrated absolute-stick control, a package registry and qualified installation/activation are separate follow-on increments. [Roadmap](../ROADMAP.md).
