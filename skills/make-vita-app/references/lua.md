# Lua workflow

Read the checkout's `SCRIPTING.md` for the actual API. Scenes return `update(dt, input)` and `draw()`, plus optional `init()`. Drawing uses `vita.rect`, `circle`, `line`, `text` and `rgb`; diagnostics use `log` and `metric`. Do not invent audio, filesystem, socket, texture or module APIs.

Limits: 16,384 UTF-8 source bytes, 1 MiB VM, 256 draw commands, eight finite numeric metrics and enforced instruction budgets. Use x=24..936, y=100..480. The host owns pause/title/footer and clamps dt to 0..0.05. Inspect input fields/button definitions before using a channel.

```powershell
.\.venv-devloop\Scripts\python.exe tools/vita_app.py new paddle --route lua --name "Vita Paddle"
.\.venv-devloop\Scripts\python.exe tools/vita_app.py check paddle
```

Edit `main.lua` and `vita-project.json` checks for the requested app. `check` runs the real shared Lua/core under host sanitizers through the pinned offline Docker toolchain. Deterministic input fixtures and numeric assertions prove host behavior, not physical controls or the Vita display.

For timing boundaries or controller traces, use the lower-level checker:

```powershell
.\.venv-devloop\Scripts\python.exe -m app_tools.lua_check SOURCE.lua --checks CHECKS.json --frames 480 --dt 0.016666666666666666 --inputs INPUTS.json
```

`CHECKS.json` is a list of metric predicates. `INPUTS.json` is an ordered list of events, for example `[{"frame":10,"buttons":16384},{"frame":11,"buttons":0}]` for a CROSS press and release. Stick fields `lx`, `ly`, `rx`, `ry` use 0..255; values persist until changed, and button edges are derived. Test phase boundaries, held input and reset behavior with app-specific predicates. Keep fixtures and reports private with the project.

For live work:

1. Obtain the installed DevLoop build from its verified report/record; read `vita_status` and `vita_script_status`.
2. Call `vita_workbench_prepare_script_session` with exact `expected_devloop_build`, keeping `allow_launch` false. If unavailable, complete source/host work and report the manual app-opening boundary.
3. Use returned `runtime_identity.pid`, `.run`, `.build_id` and `expected_revision`. `session-args` accepts saved preparation JSON and generates current source/hash/check arguments without contacting the Vita. Never bake transient pins into reusable configuration.
4. Call `vita_workbench_script_session`. Bounds: 1..8 candidates, 0.25..30 seconds measurement each, 0..3 seconds warmup, at most 120 planned aggregate seconds. Every candidate needs app-specific metric predicates.
5. Inspect acceptance, advancing frames/updates, faults and restoration. Default is the original scene paused. Use `retain_best` only when requested; it creates a fresh paused VM, not a saved measured state.

Rank normalized measurements rather than raw cumulative distance from unequal execution windows. Input/capture qualification is separate from script readiness. Scene source survives on the PC; retained VM state is lost when DevLoop closes.
