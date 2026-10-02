# Prototype tool surface

This documents the current DevLoop interface ahead of its public source import. It is not an installation guide: this repository does not yet include a runnable bridge or native app.

| Tool | Effect |
| --- | --- |
| `vita_status` | Read app mode, pause state, native parameters, frame/revision and device sample time |
| `vita_read_input` | Read physical button, stick, touch and motion observations with API status |
| `vita_get_logs` | Read bounded event logs and their sequence/sample metadata |
| `vita_screenshot` | Return a PNG of DevLoop's display with capture metadata |
| `vita_set_parameters` | Change native gravity, drag, brake or maximum speed using an expected revision |
| `vita_run_experiment` | Pause, resume, reset, recenter, select stick/tilt mode or clear native obstacles |
| `vita_stage_package` | Transfer the selected DevLoop VPK, verify its expected hash twice and return the manual install path |
| `vita_script_status` | Read script identity/hash, errors, allocation, callback timing, metrics and rollback availability |
| `vita_load_script` | Compile/preflight a bounded Lua source candidate and replace the experiment on success |
| `vita_script_control` | Restart, roll back, return to native mode or reactivate the retained current script |

The bridge also exposes scripting and example resources so a client can discover the experiment contract.

## A typical interaction

1. Read status and keep its revision.
2. Submit a named Lua script with that revision.
3. Inspect script status and its accepted source hash.
4. Resume the experiment using the current revision.
5. Read metrics and capture a screenshot.
6. Pause or recover when needed.

If a mutation times out, inspect status before making another change. Do not assume the request failed to apply. If the app is closed, asleep or unreachable, live calls report unavailability.

The exact schemas and example commands will accompany the public source and setup guide. Package staging uses the file manager's FTP endpoint independently of the running DevLoop HTTP endpoint.
