# Roadmap

The first public project is the DevLoop MCP development loop. Broader Vita projects can reuse it as integrations mature.

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
- [ ] Test the broader Control service after LiveArea starts, preserving boot recovery.
- [ ] Qualify bounded injected inputs, expiry/focus cancellation, cross-app capture and measured interaction latency.
- [ ] Coordinate native build/stage/observe workflows after those gates pass.

The original Control 0.2.0 boot activation hung and was rolled back. Inspector 01.03 establishes the read-only handoff; the broader Control service and automatic installation remain development work. [Background service](docs/RESIDENT.md), [Inspector](docs/INSPECTOR.md) and [evidence boundaries](docs/VALIDATION.md).
