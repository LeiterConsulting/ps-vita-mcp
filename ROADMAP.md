# Roadmap

The [functional MCP staging point](docs/BASELINE.md), recorded October 3, 2026, is the prerequisite for remaining autonomous development work. Every new device/build must pass its acceptance checklist before advancing. The public sources include foreground DevLoop and runtime-loaded background Control; installation remains manual.

## 1. Publish a usable developer preview

- [x] Import the focused native host, desktop bridge, build scripts and tests.
- [x] Include starter Lua examples, original screenshots and dependency notices.
- [x] Document isolated build, pairing and MCP client configuration.
- [ ] Qualify the 01.03 candidate on the device, including exit and sleep/return.
- [ ] Complete notices for all linked SDK libraries before binary distribution.
- [ ] Publish the accepted VPK with its package hash and scoped validation summary.

The working development prototype is 01.02. The imported source builds 01.03 with a graphics shutdown fix; hardware results from 01.02 do not certify that changed candidate.

## 2. Make experiments practical projects

- Persistent experiment slots and a recoverable last-good source.
- Bounded sprite/font and short-audio support.
- Clear reconnect, pairing and fault diagnostics.
- Captured sessions that relate source changes to screenshots and measured metrics.

## 3. Support additional native apps

- A reusable app integration API with declared tools and state.
- A registry of selected build/package identities.
- Native build diagnostics and verified staging for registered projects.
- One small original app and one instrumented engine integration as concrete examples.

These integrations require their own real-device proof. A successful game port is useful feasibility evidence, but does not itself demonstrate MCP control inside that game.

## 4. Explore richer development workflows

- Explicit experiment input recording/replay.
- Shared benchmark scenes and measured capture overhead.
- A desktop session viewer for scripts, captures and metrics.
- Additional host/device compatibility based on contributed test results.

Each addition should complete a useful user workflow and retain a working recovery path.

## 5. Qualify background development services

- [x] Publish Resident status/upload sources with guarded staging and manual activation.
- [x] Prove the Inspector app-to-Shell metadata handoff, caller guard and normal proxy/app cleanup on the development Vita.
- [ ] Repeat public-checkout package installation and lifecycle checks on additional devices.
- [ ] Qualify Resident during gameplay, app return, sustained transfers and sleep/wake.
- [x] Demonstrate runtime Control 0.2.2 activation through Starter after normal boot, matched readiness and normal Starter exit.
- [x] Observe screen readback in the file manager, LiveArea and DevLoop, plus managed file roundtrip/copy/hash-guarded deletion.
- [x] Observe five injected input channels in DevLoop, expiry without PC release, stale-target refusal and focus cancellation on the original development device.
- [x] Publish sources, setup, support and machine-readable baseline evidence for this staging point.
- [ ] Repeat the functional baseline with freshly built public artifacts; retain exact identities and physical observations.
- [ ] Qualify sustained interaction, sleep/wake and network-fault recovery.
- [ ] Complete one autonomous Lua edit/trial/observe/compare/rollback slice on a currently qualified session.
- [ ] Add a package registry and qualified installation/activation before unattended native VPK iteration.

The original Control 0.2.0 boot activation hung and was rolled back. Control 0.2.2 loads at runtime through Starter; it must not be added to boot configuration. Inspector 01.03 remains an optional read-only diagnostic. [Complete setup](docs/GETTING-STARTED.md), [Control](docs/CONTROL.md) and [evidence boundaries](docs/VALIDATION.md).

## 6. Deliver the Workbench preview

The October 4 development session passed hash-pinned Lua trials with restoration, separate software input channels/focus cancellation, power readbacks and managed-file recovery. The current public branch adds those workflows, source-bound candidate staging, RLE capture and clock-independent touch diagnostics.

Next: complete front/rear physical touch, motion/buttons/sticks regression, manual sleep/wake and independent Wi-Fi-loss restoration. Then install freshly built public packages and repeat their exact acceptance matrix, including DevLoop 01.03 lifecycle. Finish dependency notices and the clean-machine setup trial before publishing signed checksums and a preview release. Native installation remains an operator step; full unattended native iteration follows a separately qualified install/activation design. See [the release checklist](docs/RELEASE-CHECKLIST.md).
