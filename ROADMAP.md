# Roadmap

The first public project is the DevLoop MCP development loop. Broader Vita projects can reuse it as integrations mature.

## 1. Publish a usable developer preview

- Import the focused native host, desktop bridge, build scripts and tests into this repository.
- Include starter Lua examples and upstream dependency notices.
- Replace development-machine assumptions with documented configuration.
- Complete release-candidate exit and sleep/return verification.
- Provide a VPK, package hash, build instructions, pairing/setup guide and scoped validation summary.

The working development prototype is 01.02. Public release numbering will be established when the imported candidate is qualified.

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
