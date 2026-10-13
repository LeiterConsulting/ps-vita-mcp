# Resident transport diagnostics

Status date: October 12, 2026. **Source candidate 0.1.7; hardware activation and
qualification pending.** The installed Vita still runs 0.1.6. Its intermittent
HTTP timeouts block qualification of a complete native development cycle.
[Installed identity and lease evidence](RESIDENT-KEEP-AWAKE.md) remain separate.
[Source-bound candidate validation](resident-transport-validation.json) records
the exact package and host checks; its hardware gates remain pending.

The candidate adds observability to the existing keep-awake worker on port
**17869**. It retains the two-second accepted-client budget, ten-millisecond
would-block polling, twenty-millisecond idle polling, worker priority and stack,
automatic-suspend-only ticks and current listener recovery behavior. It adds no
boot entry, launcher, persistent power lock or mutation retry.

## Read-only tools

The combined source bridge exposes **42 tools**: thirteen Resident, thirteen
Control and sixteen Workbench. Restart the PC Resident MCP connection after
updating its source. Discovery alone does not activate the native capability.

| Tool | Purpose |
| --- | --- |
| `vita_resident_keep_awake_transport_status` | Read retained sequence range, socket/listener counters and raw network observations |
| `vita_resident_keep_awake_transport_record` | Read one completed connection record by its 16-character lowercase hexadecimal sequence |

Both tools use the desktop administrator credential. Companion inspection
credentials do not grant access. They send GET requests only, have a five-second
absolute PC deadline, validate the complete bounded response and do not renew a
lease. Use exact build and power-instance pins to bind a record to the status
that identified it. An old service reports an unsupported route; the client
does not emulate diagnostics or fall back to a mutation.

Status accepts optional `resident_build_id` and `instance_id` pins together.
Record requires both pins plus `sequence`; use the power instance from the
transport status, which differs from Resident's main/native lifecycle instance.

Native routes are `GET /keep-awake/transport-status` and
`GET /keep-awake/transport-record/<16-lowercase-hex>`. Each JSON response is at
most **1399 bytes**. Recognized diagnostic requests, including unauthorized
ones, are excluded from the connection ring. Reading a dump therefore does not
overwrite the records being retrieved; aggregate diagnostic/accept counters
can still advance. Malformed routes can create ordinary failure records.

## What a trace establishes

One worker owns a static ring of **16 completed records and one current record**,
with each record at most **192 bytes**. Records contain numeric metadata only:
timestamps, counters, revisions, enumerated phases and raw syscall results.
They contain no bearer tokens, lease/job identifiers, request headers, request
bodies, file paths or screen contents. The ring is volatile and disappears on
reboot. Resource sampling is explicitly disabled for this candidate.

Each completed connection retains offsets from accept for first receive,
header completion, body completion, policy apply before/after, first header
bytes queued, response completion and close. Missing offsets are `4294967295`.
It also retains received/header/body byte counts, would-block counts, policy
revision before/after, apply result, HTTP status, final I/O result with immediate
errno, close result, tick counts and the largest observed worker-step gap.

`phase_ms` uses the order above. `bytes` means received, header queued and body
queued. `would_block` means receive and send. `revision` means immediately
before/after policy apply when flag 4 is set, otherwise request entry/close.
`tick_count` always means request entry/close. I/O stage/result/errno describe
the last receive or send call; a successful call has errno zero, and close is
stored separately. Method values are 0 unknown, 1 GET and 2 POST. Operation values
are 0 unknown, 1 status, 2 begin, 3 renew and 4 end. Outcome values are:

| Value | Outcome |
| --- | --- |
| 0 | Pending |
| 1 | Complete response queued |
| 2 / 3 | Receive / send deadline |
| 4 | Receive EOF |
| 5 / 6 | Receive / send error |
| 7 | Framing failure |
| 8 | Worker stopped |
| 9 | Clock regression |
| 10 | Response formatting failure |

Flags are additive: 1 clock regression, 2 saturated offset, 4 policy apply
called, 8 response queued and 16 close failed. Socket stages are 0 none,
1 socket, 2 reuse option, 3 bind, 4 listen, 5 listener nonblocking,
6 accept, 7 client nonblocking, 8 receive, 9 send and 10 close.

The summary retains listener generations and failures, accept failures, raw
NetCtl return/state, transition count, last loss and maximum step gap. One raw
network observation supplies both policy and tracing; there is no second
NetCtl getter per step. A recovered listener retains its latest failure so a
later read can still inspect it.

Last loss retains the latest unhealthy transition or initial unhealthy
observation, with defaults result 0, state -1 and timestamp 0. Current network
result/state remain the latest observation. A listener failure can include a
best-effort reuse-option failure even when opening succeeded; `listen_failures`
counts failed listener creation only.

**Queued bytes are not proof that the PC received them.** A trace can identify
an accepted policy change with zero response bytes queued. It cannot, by
itself, establish over-the-air delivery, peer receipt, autonomous Wi-Fi
reassociation, full suspension or the cause of every main-service timeout.
The ring instruments the lease port; bulk uploads use the separate main port.

## Qualification sequence

1. Run C policy, diagnostic boundary and actual HTTP tests under sanitizers;
   run strict GET-client, stdio bridge and guarded staging tests. Build the
   ARM plugin with the pinned SDK and bind its hash to the source manifest.
2. Stage the exact candidate, config proposal and rollback using two readbacks.
   Preserve the installed 0.1.6 artifact and active configuration. Activation
   requires the operator's normal reboot; keep withdrawn boot helpers disabled.
3. Verify normal boot and exact build identity, then inspect diagnostics through
   fresh PC tools. Verify authorization failures, bounded records and retrieval
   without ring overwrite. Compare before/after revision and tick observations.
4. Run a bounded lease hold and correlate each PC receipt with a native record.
   On uncertainty, retain the original job and read diagnostics; never replay an
   uncertain mutation. Release the lease and confirm ordinary sleep separately.
5. Reproduce the intermittent transport failure and qualify any resulting fix
   before resuming native installation/redeployment tests. Cross-build native
   ownership adoption remains a separate implementation gate.

Host tests and ARM packaging do not qualify hardware. A new plugin build does
not inherit the installed 0.1.6 lease results or historical 0.1.5 native cycles.
