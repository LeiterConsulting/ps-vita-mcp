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

Each addition should complete a useful user workflow and retain a working recovery path. Kernel/system integration and automatic installation need separate proposals rather than being implied by the initial MCP bridge.
