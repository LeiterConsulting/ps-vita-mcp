# Live Lua experiments

DevLoop supports edit/push/run without rebuilding or reinstalling a VPK for each script change. This interface was exercised on prototype 01.02 and is retained in public candidate 01.03. The PC bridge exposes ten tools. `vita_load_script` sends text and its SHA-256 to the running app; the main thread creates a fresh Lua VM, compiles the source, runs init plus one update with dt=0 and cleared button edges, and checks draw. Only a successful candidate replaces the current VM. A failed edit keeps the current script and its state. Loading, restarting, rolling back and changing modes always start paused.

Follow [setup and pairing](docs/SETUP.md), then leave DevLoop open on Wi-Fi. [Validation](docs/VALIDATION.md) distinguishes prototype hardware results from pending 01.03 device qualification.

## Quick start

From the project directory:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\bounce.lua --resume --capture
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\input_scope.lua --resume --capture
```

To push each saved edit, explicitly start the foreground watch command:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\run_script.py experiments\bounce.lua --resume --capture --watch
```

Watch runs only while that command is running. Ctrl+C stops it. A failed change is reported once for that content hash; it is not replayed automatically. Save new content to try another edit. If a mutation times out, inspect status before choosing another action. Captures and receipts are written to a fresh `evidence/devloop/script-session-*` directory.

Through MCP, read `vita_status`, then call `vita_load_script(name, source, expected_revision)`. Read `vita_script_status` for accepted hash, error, custom metrics and limits. Use `vita_run_experiment("resume", revision)` to run. `vita_script_control` accepts `restart`, `rollback`, `native`, or `activate`. The six original experiment tools and package staging remain available; native physics commands require native mode.

## Script interface

Source is Lua 5.4 text, up to 16,384 UTF-8 bytes without NUL or binary control bytes. Name is 1..32 ASCII letters, digits, underscores or hyphens. A script returns a table with required `update(dt, input)` and `draw()` functions, plus optional `init()`:

```lua
local x = 480
local teal = vita.rgb(64,220,191)
return {
  init = function() vita.log("Ready") end,
  update = function(dt, input)
    x = math.max(20, math.min(940, x + (input.lx-128)/127*200*dt))
    vita.metric("x", x)
  end,
  draw = function()
    vita.rect(24,100,912,380,vita.rgb(20,32,49))
    vita.circle(x,285,18,teal)
    vita.text(44,140,1,teal,"Hello from live Lua")
  end
}
```

`dt` is seconds, clamped to 0..0.05. Pausing freezes updates; draw still runs. Long sleep/resume gaps pause the host and discard elapsed time. START toggles pause for a healthy script; START+SELECT exits the app. Other controls belong to the script while Lua is active. When returning to native mode, the native world's settings and state are retained.

Input is a fresh table with `buttons`, `pressed`, `controller_result`, raw `lx/ly/rx/ry` values 0..255, `fps`, and `resumed`. `front` and `rear` contain up to eight contacts, indexed from 1. Each has `id`, normalized `x/y`, and `raw_x/raw_y`; the panel table also includes `read_result`. `motion` has `read_result`, `ax/ay/az` acceleration and `gx/gy/gz` angular velocity. Read results distinguish unavailable sensors from a zero reading. DevLoop reads effective platform input. Its own ten-tool bridge does not inject controls; the separate [Control service](docs/CONTROL.md) can add bounded synthetic input. The [input proof](experiments/mcp_input_proof.lua) observes that delivery and neutral return; human controller acceptance remains separate.

Button constants are in `vita.buttons`: SELECT, START, UP, RIGHT, DOWN, LEFT, L, R, TRIANGLE, CIRCLE, CROSS, SQUARE. Lua 5.4 bitwise syntax checks a held button with `input.buttons & vita.buttons.CROSS ~= 0`, or an edge with `input.pressed`.

| API | Arguments and behavior |
| --- | --- |
| `vita.width`, `vita.height` | 960 and 544 |
| `vita.rgb(r,g,b)` | 0..255 channels; returns an opaque uint32 colour |
| `vita.rect(x,y,w,h,colour)` | Buffered filled rectangle |
| `vita.circle(x,y,radius,colour)` | Buffered filled circle |
| `vita.line(x1,y1,x2,y2,colour)` | Buffered line |
| `vita.text(x,y,scale,colour,text)` | System font; scale 0.25..3, up to 96 printable ASCII characters |
| `vita.log(message)` | Up to 100 bytes, eight buffered messages; inspect with `vita_get_logs` |
| `vita.metric(name,value)` | Up to eight numeric metrics, names 1..24 ASCII letters/digits/underscores, finite values within +/-1e9 |

Drawing calls are allowed only inside draw(). The host buffers at most 256 commands, then renders them after a successful callback. Host chrome occupies the title/status and footer; experiments should use x=24..936, y=100..480. Coordinates and sizes are bounded; invalid or non-finite arguments fault the script. All scripts can use math, string, table, utf8 and a reduced base library. File, process, module, debug and coroutine libraries are not exposed. Dynamic load, metatable access, collectgarbage, pcall/xpcall and string.dump are disabled; the host handles errors and instruction hooks.

## Recovery and diagnostics

Each VM has a 1 MiB Lua allocation budget. The current VM, one rollback VM and a temporary candidate may coexist. Init/chunk preparation has a 60,000-instruction budget; update/draw have 20,000 each, checked every 100 instructions. The source compiler and C library routines are bounded by source/memory limits; instruction hooks are not a hard wall-clock deadline for every C routine. This is a development containment mechanism, not a general security boundary for hostile scripts.

A later update/draw error marks the current VM faulted, pauses execution, reports name/line/message in MCP and on the device, and leaves HTTP available. Resume is rejected until a successful reload, restart or rollback. Rollback restores the previous healthy VM and its retained state. Restart reconstructs the current source and resets its Lua state. Native fallback returns to the existing Tilt Playground. Scripts and rollback state are held in RAM in this slice; closing the app loses them, while PC source files remain.

`vita_script_status` reports source hash/size, current and previous names/hashes, fault/rollback flags, updates, drawing count, current/peak Lua allocation, callback CPU time samples and custom metrics. Timing uses the platform C clock and needs physical qualification; it is not a frame-latency guarantee. `vita_screenshot` still captures the app's actual display with frame/revision metadata.

The engine uses the official [Lua 5.4.9 archive](https://www.lua.org/ftp/) and its published SHA-256, vendored with its MIT notice. Host and ARM builds use the same source; no JIT or additional kernel plugin is required. The [Lua manual](https://www.lua.org/manual/5.4/manual.html) documents the allocator, protected calls, text-only loading and instruction hooks used here.

## Acceptance

PC proof exercises the real Lua engine, core and native HTTP source under sanitizers, plus MCP stdio against explicit fixtures. `bridge/prove_scripts.py` is the separate real-Vita acceptance pass: push/run/capture both experiments, reject bad syntax and an infinite loop, hot reload a visible change, roll back, test a later runtime fault and recover to native paused mode. A successful build or FTP receipt does not establish this new installed-runtime proof or physical human-input/sleep acceptance.
