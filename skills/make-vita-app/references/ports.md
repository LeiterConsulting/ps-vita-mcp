# Port or feasibility workflow

Start from actual source revision, license and assets. Inspect local source first; read referenced upstream primary sources when needed. Use official project/SDK documentation for uncertain technical facts. Android-derived wrappers do not imply general Android/APK support.

Write a concrete proposal covering:

- User-visible result, controls and required delivery form.
- Upstream revision/license, dependencies, available test assets and missing source/data.
- Compiler/language, CPU assumptions, threads/JIT, graphics/shaders, audio, saves/files and networking.
- Actual pinned SDK libraries and relevant hardware probes. Keep budget estimates separate from measurements.
- The smallest representative slice: one scene/level/audio stream/save roundtrip or host-tested simulation. Choose a test that can reject the route.
- Acceptance criteria, remaining human checks, risks and fallback.

Plan-only requests stop before implementation/device writes. Implementation requests produce a feasible slice and iterate real checks; do not substitute a stock example and call the port complete.

Use Lua only when its APIs cover the slice. Use the native slot for small compiled prototypes in its fixed layout. A distinct title or arbitrary VPK needs its own registration/installer/runtime adapter and device qualification; independent source/build work may proceed. Keep proprietary assets and private app code out of public source.
