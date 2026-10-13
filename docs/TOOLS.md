# MCP tool surface

The foreground DevLoop bridge in `bridge/server.py` exposes these ten tools through MCP stdio. The separate combined Resident bridge exposes [thirteen Resident](RESIDENT.md), [thirteen Control](CONTROL.md) and [sixteen Workbench tools](../workbench/README.md), for 42 total. Three native lifecycle tools require the Resident 0.1.5 candidate and dedicated Lifecycle Lab; five native Lab cycles across two builds passed; same-build journal durability passed after a normal reboot without replay. Workbench includes Control-free preparation and multi-candidate Lua sessions on already open DevLoop 01.04. Follow [complete baseline setup](GETTING-STARTED.md), [autonomous preparation](AUTONOMOUS-DEVLOOP.md) or [DevLoop-only pairing](SETUP.md). Clients can discover exact argument schemas through MCP `tools/list`.

The earlier refreshed registered PC Resident MCP exposed all 36 tools and passed direct status, an unexecuted native preview and GET-only reconciliation of the completed post-reboot job. [Registered-client qualification](NATIVE-LIFECYCLE.md#registered-mcp-readiness-pass).

Resident 0.1.6 adds four [bounded keep-awake tools](RESIDENT-KEEP-AWAKE.md): status, begin, renew and end. Native jobs acquire/release leases automatically; status and preview never renew. Other workflows use explicit tools or the PC command wrapper. Live qualification is recorded separately.

Source candidate 0.1.7 adds two administrator-only, read-only [transport
diagnostic tools](RESIDENT-TRANSPORT.md): `vita_resident_keep_awake_transport_status` and
`vita_resident_keep_awake_transport_record`. Their native routes are not implemented by
the installed 0.1.6 service; hardware activation and qualification are pending.

| Tool | Effect |
| --- | --- |
| `vita_status` | Read app mode, pause state, native parameters, frame/revision and device sample time |
| `vita_read_input` | Read effective platform button, stick, touch and motion observations with API status; Control emulation may contribute |
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

`vita_load_script` takes `name`, `source` and `expected_revision`. Mutating experiment/script tools also require `expected_revision`; `vita_stage_package` instead requires the selected VPK's `expected_sha256`. Read-only tools take no arguments. Package staging uses the file manager's FTP endpoint independently of the running DevLoop HTTP endpoint.
