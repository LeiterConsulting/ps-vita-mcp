# Resident transport diagnostics

Status date: October 13, 2026. **Resident 0.1.7 is running with its exact build
verified; qualification is partial.** Its intermittent
HTTP timeouts block qualification of a complete native development cycle.
[Installed identity and lease evidence](RESIDENT-KEEP-AWAKE.md) remain separate.
[Source-bound candidate validation](resident-transport-validation.json) records
the exact package, host checks and current hardware results.

The candidate adds observability to the existing keep-awake worker on port
**17869**. It retains the two-second accepted-client budget, ten-millisecond
would-block polling, twenty-millisecond idle polling, worker priority and stack,
automatic-suspend-only ticks and current listener recovery behavior. It adds no
boot entry, launcher, persistent power lock or mutation retry.

## Read-only tools

The combined source bridge exposes **42 tools**: thirteen Resident, thirteen
Control and sixteen Workbench. Restart the PC Resident MCP connection after
updating its source. Discovery alone does not activate the native capability.
Direct registered main, power and diagnostic status calls passed on the current
build. Current enabled-tool metadata enumerated all 42 names: thirteen Resident,
thirteen Control and sixteen Workbench. Metadata enumeration does not qualify
every runtime operation or prove the existing process loaded the new PC deadline
correction; its restart is pending.

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

### October 13 hardware results

Registered tools confirmed Resident **0.1.7**, build
`1a626d099f643cf50c7ad64ddbdfd40c44eb65c7e2371102a5c6195472a7bc4a`,
plugin SHA-256
`986527244c745b978a596f260b1ddbe2311cbe9eb7ba9558ca8e581284b9ec8e`.
Authenticated status and record retrieval, an invalid-credential HTTP 401, and
zero-sequence `not_found` passed. Thirteen record/status reads preserved ring
count 12, bounds `1..c` and overwrite count 0. The separate authorization and
absence checks also left those bounds unchanged.

The planned 90-second lease hold **failed after 36.44 seconds**: two renewals
succeeded, then the third renewal's preflight GET timed out in PC
`read_headers`. No third renewal POST or mutation replay occurred. Cleanup
confirmed end at revision `3→4`, tick count 39, 38.60 seconds after keeper start.
There were no application effects.

All 12 native records show complete replies queued, successful closes and
completion offsets of 0–1 ms, without recorded receive/send deadlines,
would-block calls or socket errors. The matching GET, sequence `9`, queued
116 header bytes and 480 body bytes at offset 0 ms. The listener retained
generation 1 with no listen/accept failures; the largest observed worker gap
was 27 ms, and the latest recorded network loss preceded the hold.

This narrows the failure without identifying its cause. Local queueing does
not prove PC delivery. PC `read_headers` includes `getresponse()` and its
following absolute-deadline check, so it does not prove that no header bytes
reached the PC. Unsynchronized clocks and the absence of request identifiers
also limit correlation. A later direct registered record read timed out without
mutation. PktMon status access was denied by its driver; no capture or host
network setting change occurred. The subsequent probes are recorded below. The operator
confirms current standby is 30 minutes. Remaining awake after release at that
setting does not qualify sleep after a one-minute interval. The physical
normal-boot gate and current-build sleep remain unqualified.

Remote CI run `38340297125` passed at source commit `22ea7fb`. Public validation
retains hashes of the local receipts; raw evidence and private Companion code
remain excluded. Earlier 0.1.6 lease/sleep results remain historical evidence.

### October 13 PC receive probes and deadline correction

An A/B observation completed **8 of 8 status GETs in 30.667 seconds**: four
production-client requests and four raw-socket requests, each matching one
native record. No timeout or parser defect was reproduced. Diagnostic GETs
before each trial warmed the link, and instrumentation may affect timing;
this does not reproduce isolated ten-second renewal cadence.

A subsequent planned 90-second hold, without intermediate diagnostic reads,
**failed after 85.011641 seconds**, after six renewals. Its seventh renewal
stopped in the preflight GET; no seventh-renewal POST was submitted. Connection
15 returned zero response bytes to Python. The watchdog called shutdown at
5013 ms, while the raw receive returned a timeout at 5629 ms. Matching native
sequence `24` queued 116 header bytes and 484 body bytes within 1 ms and closed
successfully. Cleanup confirmed end at revision `11→12`, tick count 128.
No app effects or mutation replays occurred. The endpoint failure's cause is
unknown; the PC read exceeded the intended total budget despite the watchdog.

The public [`http_deadline.py`](../resident/http_deadline.py) helper now applies
the **remaining** budget before connect, each send and every raw read beneath
the buffered HTTP parser. The five-second overall deadline, watchdog, final
checks and no-replay policy remain. All **75 focused client tests** passed
(8 new deadline, 41 lease and 26 diagnostic-client tests), as did six private
probe smoke cases. Native plugin bytes are unchanged. This corrects PC budget
enforcement without establishing why a queued reply was unavailable.

A fresh-process instrumented hold with the corrected PC source **passed
90.0004986 seconds**, with eight renewals, zero errors and confirmed end.
All 22 connections returned response bytes; the maximum observed connection
time was 3108.34 ms. One request retransmitted 204 bytes. The lease began at
revision 13 and ended at revision 22, tick count 218; 16 native records were
retained. This is one bounded pass at unchanged **30-minute standby**, not a
delivery-root-cause fix, broad reliability guarantee, one-minute sleep test or
native app cycle. No mutation was replayed and no app effects occurred.
The public validation binds the exact three PC source hashes and retained
proof SHA-256. Fresh host stdio fixtures also passed 20 bridge checks and 16
file-MCP checks, and all 41 native-lifecycle PC tests passed. These host results
do not qualify every registered tool on the Vita. The existing registered MCP
process still needs a restart to load the PC correction.

The private Windows TCP-info probe passed six fake-DLL tests and a localhost
check with eight snapshots: known payload bytes were counted before the app
read them, with a maximum snapshot time of 0.110 ms. Four subsequent Vita GETs
all passed and matched four ordered native records. On the fourth, Windows
reported 408 bytes out and 204 retransmitted bytes for a 204-byte GET; 534 bytes
in matched Python's received total. This shows request TCP retransmission on
one successful connection, not the cause of the failed reply. These historical
trials ran private probe copies; reusable generic probe sources are now public.
Raw receipts remain ignored. Standby remained 30 minutes;
these observations add no physical-sleep or native-cycle acceptance.

### Public PC probes

[`probe_resident_transport.py`](../tools/probe_resident_transport.py) provides
the bounded GET-only comparison; [`resident_tcp_info.py`](../tools/resident_tcp_info.py)
provides Windows localhost qualification and `query(sock)`, which returns numeric
TCP metadata. Six public probe smoke cases and six TCP fake-DLL tests passed.
The public probe recomputes its remaining budget before each raw connect,
send and receive. The Windows TCP utility's public localhost CLI also passed.
The latest CI configuration has 33 groups; the earlier 32-group pass predates
these sources, and latest-source CI is pending.

```powershell
.\.venv-devloop\Scripts\python.exe tools/probe_resident_transport.py --smoke
.\.venv-devloop\Scripts\python.exe tools/probe_resident_transport.py --resident-build-id BUILD_ID --instance-id POWER_INSTANCE_ID --output evidence/resident/fresh/proof.json
.\.venv-devloop\Scripts\python.exe tools/resident_tcp_info.py qualify-localhost
```

`--smoke` and localhost qualification do not contact the Vita. The middle
command requires the awake Vita, its configured administrator endpoint and exact
build/power-instance pins; it sends bounded status GETs without a lease or app
effects. Output receipts stay under ignored `evidence/resident/`; localhost
qualification also chooses an ignored evidence directory automatically. Public
generic tools contain no device credentials or iPhone implementation.

### Repeatable qualification procedure

The installed binary binds the original working source bytes. A retained CRLF
variant in `resident/service.c` means the repository's canonical LF checkout
has a different native fingerprint, even though the only difference is line
endings. The validation record lists both fingerprints and three source-byte
variants. A fresh LF build needs its own hardware qualification; this PC
correction did not change the installed plugin.

The current staging, runtime-identity and read-only results above complete
parts of this procedure. Physical normal boot, sustained work and sleep remain
separate gates; the steps also apply to future replacements.

1. Run C policy, diagnostic boundary and actual HTTP tests under sanitizers;
   run strict GET-client, stdio bridge and guarded staging tests. Build the
   ARM plugin with the pinned SDK and bind its hash to the source manifest.
2. Stage the exact candidate, config proposal and rollback using two readbacks.
   Preserve the previous plugin artifact and active configuration. Activation
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
not inherit the historical 0.1.6 lease results or 0.1.5 native cycles.
