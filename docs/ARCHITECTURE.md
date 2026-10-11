# Architecture

## The first implementation

Vita DevLoop has two cooperating components:

| Component | Responsibility |
| --- | --- |
| Desktop MCP bridge | Expose tools and resources, authenticate device requests, return images/structured results, and perform verified package staging |
| Native Vita host | Read hardware, run the native or Lua experiment, draw the scene, apply queued changes, publish snapshots and capture its framebuffer |

The desktop bridge uses Python and MCP over stdio. The Vita host uses C, libvita2d and Lua 5.4.9. The source includes Lua provenance and a digest-pinned VitaSDK container in `toolchain.lock.json`.

## Commands and observations

Mutations carry an expected revision. The app applies them on the main thread between simulation frames and publishes the resulting snapshot before acknowledging completion. Local interactions can also change that revision.

A stale revision is rejected. A timed-out change is not silently replayed: the client reads status to establish what happened before choosing another action. Frame/revision metadata ties an observation to the app state it captured.

## Lua replacement and recovery

A candidate script is compiled in a fresh VM and preflighted before becoming active. A rejected candidate leaves the current script intact. A successful candidate starts paused, and one previous VM can be retained for rollback.

Runtime callback failures pause the experiment and report the error while keeping inspection available. Restart reconstructs the current script; rollback selects the retained prior VM; native fallback returns to the built-in experiment.

The prototype limits source, allocations, instructions and drawing commands. These limits provide development containment, not a security boundary for hostile code.

## Capture and input

Screenshots capture DevLoop's own framebuffer, with copying coordinated on the main thread and PNG encoding handled by the network worker. This is an on-demand still image, not system-wide video capture.

Input observations include read status alongside values so an unavailable sensor can be distinguished from a zero reading. DevLoop's own bridge reads input; the separate Control bridge can submit bounded synthetic input that DevLoop observes through the effective platform APIs. Neither a synthetic trial nor its receipt substitutes for physical controller acceptance.

## Packaging and installation

Native app updates use a separate path: build and validate the selected package, upload to a fresh FTP inbox as a temporary file, read it back and verify its hash, rename it, then verify the final file again. The user installs it through the Vita file manager.

The existing uploader accepts the DevLoop identity. General project/package support will need an explicit registry and its own validation.

## Reuse beyond DevLoop

The separate `resident/` service runs in SceShell and serves background status and a verified upload inbox on port 17866. Its four native-service tools read its own pairing config. It does not depend on DevLoop being open. Native activation is a guarded configuration proposal followed by a manual copy/reboot. [Resident design and setup](RESIDENT.md).

The combined `resident/bridge.py` registers four Resident, thirteen Control and eleven Workbench tools, for twenty-eight total. Control runs on port 17867 with Resident pairing. The existing manual Starter path loads a matched kernel helper once, checks readiness through an own-process proxy, releases that proxy, and loads the Shell service with zero arguments. The Shell-caller guard, matching ABI/fingerprint and on-storage one-load marker constrain the session. Starter exits while the pair remains loaded until reboot. The full Control pair must not be added directly to boot configuration.

The independent [one-shot startup experiment](../resident/autostart/README.md) starts a worker and returns from the loader entry point. The worker waits for delayed LiveArea readiness, consumes a default-disabled explicit opt-in, retains cross-Starter duplicate-load guards, verifies exact native files, validates a temporary Shell metadata probe, then submits the service. It never retries a submission or unloads the Control pair. External network identity and native boot acceptance remain separate; repeating startup across boots is not implemented. [Current autonomous scope](AUTONOMOUS-DEVLOOP.md).

Control reads the displayed framebuffer through process-aware SDK APIs. It returns bounded preview/detail RGB images, metadata and hashes, then encodes PNG on the host. Copies can span rendered frames. Its synthetic full-state leases last 16–1000 ms and cancel on display-focus changes. Managed files use fresh revision directories and exact-hash readback/deletion; system and installed-app writes are outside this API. [Control arguments and lifecycle](CONTROL.md), [complete activation/reboot procedure](GETTING-STARTED.md).

`resident/inspector/` is a separate diagnostic app. It loads a tiny metadata-only kernel helper once per session, checks its own caller through a temporary proxy, then optionally loads a read-only proxy inside SceShell. The Shell handoff uses a fresh validated on-disk session record and exact-build/nonce completion checks. User proxies are released after completed checks; the syscall-exporting kernel is retained until reboot. [Inspector lifecycle](INSPECTOR.md).

A later native integration layer could expose app-specific observations and commands inside other homebrew projects. Each app would define its supported operations, lifecycle and state model. The existing protocol and client behavior provide a starting point; a reusable integration library has not been released or validated yet.

## Workbench execution and temporary power

Workbench owns a shared process lock across Control and foreground requests for a bounded job. Profiles bind the Lua source hash, duration, input schedule and metric predicates. A journal is flushed before every mutation. Healthy increasing frames, pinned Control identity and script ownership/revision are checked; failure prevents further scheduled input. Cleanup restores the prior experiment paused only when ownership still matches. An uncertain reply is observed, never automatically replayed.

Preparation can submit one DevLoop launch after a transport failure and reconcile its result through runtime observations. Preparation and trials freeze the foreground endpoint and effective Control endpoint, including port overrides, so launch, heartbeat and cleanup cannot move to another device after a configuration change. Drift is detected through the original configuration providers.

Lua runtime readiness is separate from foreground input identity. DevLoop 01.04 publishes native `title_id`, PID, per-process `run` and source `build_id` in successful status, script, input and log responses. Preparation/trials pin this complete identity and stop after runtime changes. Input readiness/trials require an exact caller-supplied expected DevLoop build and the native PID matching a fresh Control capture before loading the scene and before each input. Script-only work may omit the expected build pin. A healthy 01.02/01.03 legacy endpoint remains script-only; a stable captured PID alone does not authorize input. Installed 01.04 passed its native runtime and Lua reload/recovery checks; mapping against Control captures, synthetic input and lifecycle acceptance remain open.

A separate heartbeat renews only the native power lease while work continues. Native timers and activity observation are independent of HTTP request frequency. Touch hooks capture native samples before injection; foreground reader slots and source advancement determine freshness in kernel receipt time. Input/frame wire ABI 2 and matched source fingerprints protect cross-process requests. Motion sampling is owned only during work when started by the service.
