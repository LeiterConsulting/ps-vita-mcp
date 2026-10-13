# Resident keep-awake lease

As of October 13, 2026, **Resident 0.1.7 is running with its exact build verified
through registered tools**. Its plugin SHA-256 is
`986527244c745b978a596f260b1ddbe2311cbe9eb7ba9558ca8e581284b9ec8e`
and its Resident build ID is
`1a626d099f643cf50c7ad64ddbdfd40c44eb65c7e2371102a5c6195472a7bc4a`.
Authenticated read-only diagnostics preserve the ring, but a planned 90-second
hold stopped after 36.44 seconds on a PC GET timeout. Cleanup confirmed release.
**Keep-awake qualification remains incomplete.** Exact runtime identity does
not confirm the physical normal-boot gate. Earlier plugins remain available for
rollback. [Current diagnostic validation](resident-transport-validation.json)
and the [historical lease record](resident-keep-awake-validation.json) keep
host, packaging, API and physical results separate.

The lease is designed to keep an already awake Vita available while a bounded development
job runs. When the job finishes, loses its connection or stops renewing, Resident
stops refreshing the automatic suspend timer and allows the Vita's normal idle
policy to act. The timing depends on existing system timers; a full configured
interval starting at lease release has not been established.
No saved sleep setting, brightness, input state or boot configuration is changed
by a lease. An already suspended Vita still needs a physical wake.

## Interim hardware results

### October 13: Resident 0.1.7

Direct registered main, power and diagnostic status tools confirmed the exact
running build. Current enabled-tool metadata enumerated all 42 source names
(13 Resident, 13 Control and 16 Workbench). This is not runtime qualification
of every tool or proof the existing registered process loaded the PC correction;
its restart is pending. Administrator rejection
(HTTP 401), zero-sequence `not_found` and retained-ring checks passed.

The planned 90-second hold **stopped after 36.44 seconds**. Two renewals
succeeded, but the third renewal's preflight GET timed out in PC `read_headers`,
before any third-renewal POST. Cleanup confirmed release at revision `3→4`,
tick count 39, 38.60 seconds after keeper start. No application effects or
mutation replays occurred.

All 12 native records show complete queued replies and successful closes,
with completion offsets of 0–1 ms and no recorded receive/send deadlines,
would-block calls or socket errors. Sequence `9`, matching the failed GET,
queued 116 header bytes and 480 body bytes at offset 0 ms. The listener had no
listen/accept failure, the maximum observed worker gap was 27 ms, and the latest
recorded network loss preceded this hold. Thirteen diagnostic reads left
count 12, bounds `1..c` and overwrite count 0 unchanged.

These records narrow the failure without establishing its cause. Queueing does
not establish PC receipt; `read_headers` includes parsing and its following
absolute-deadline check. A later direct registered record retrieval also timed
out without mutation. Subsequent PC probes and the deadline correction are
recorded below. PktMon status access was denied by its driver; no capture or host network
setting change occurred. The operator reports the Vita still awake after
release. The operator confirms current standby is 30 minutes; remaining awake
at that setting does not qualify one-minute sleep behavior. Current-build
physical sleep remains unqualified. [Diagnostic interpretation and limits](RESIDENT-TRANSPORT.md).

### October 13 PC deadline follow-up

Eight paired production-client/raw-socket status GETs passed in 30.667 seconds,
with eight matching native records. A diagnostic GET before each trial warmed
the link, so this does not qualify isolated renewal cadence or reproduce the
earlier timeout. A subsequent planned 90-second hold without intermediate
diagnostic reads **failed after 85.011641 seconds**, after six renewals.
The seventh renewal stopped during its preflight GET, with no POST submitted.
Python received zero response bytes. Watchdog shutdown occurred at 5013 ms,
but the raw receive timed out at 5629 ms. Native sequence `24` queued
116 header bytes and 484 body bytes within 1 ms and closed successfully.
Cleanup confirmed release at revision `11→12`, tick count 128, without replay
or app effects. The endpoint failure cause remains unknown.

The public PC helper now reapplies the remaining five-second budget before
connect, each send and each raw read beneath the HTTP buffer. The watchdog,
final checks and no-replay rule remain; native plugin bytes are unchanged.
All 75 focused client tests passed (8 deadline, 41 lease and 26 diagnostics),
plus six private probe smoke cases. A corrected fresh-process instrumented
hold then **passed 90.0004986 seconds**: eight renewals, zero errors and confirmed
end. All 22 connections returned response bytes, with a maximum observed
connection time of 3108.34 ms; one request retransmitted 204 bytes. The lease
began at revision 13 and ended at revision 22, tick count 218, with 16 native
records retained. This is one pass at unchanged 30-minute standby. It does not
erase the earlier failures, establish their cause, qualify broad reliability,
test physical one-minute sleep or complete a native app cycle. The public
[validation](resident-transport-validation.json) pins the PC source and proof hashes.

Fresh host stdio fixtures passed 20 bridge checks and 16 file-MCP checks;
all 41 native-lifecycle PC tests passed. These are separate from the metadata
enumeration and direct registered status calls. The registered MCP process
still needs a restart to load the deadline correction.

A private TCP-info probe passed six fake-DLL cases and eight localhost
snapshots, counting known payload bytes before app reads with at most
0.110 ms per snapshot. Four live GETs then passed and matched ordered native
records. The fourth showed 408 bytes out and 204 retransmitted bytes for a
204-byte GET; Windows counted the same 534 received bytes as Python. That is
request-retransmission evidence on a successful connection, not an explanation
for the failed reply. Those trials ran private probe copies; reusable
[generic PC probes](RESIDENT-TRANSPORT.md#public-pc-probes) are now public,
with six smoke and six TCP fake-DLL tests passed. Raw receipts remain ignored.
Standby stayed at 30 minutes; no current-build sleep or native-cycle gate passed.

### Historical Resident 0.1.6 results

The following results belong to Resident 0.1.6, plugin SHA-256
`dd8da21847f5341bc70112f86176e2f864c92b10aaeb3400ec9855751a6b1ef8`,
build `47ece86ad3b5258b6a52b4aaffefb8046e5af48c69f49a763001bf36bd815240`.
They do not qualify the current 0.1.7 build.

On that two-second-budget build, fresh actual stdio MCP
exposed all 40 tools and passed status, begin, renew and end. The trial started
inactive, observed successful ticks, ended the exact owner and observed no tick
growth afterward.

Its subsequent planned 120-second hold at one-minute standby **stopped after
about 40 seconds**. A renewal POST timed out while reading response headers
under the PC's five-second HTTP deadline. Cleanup read revision 7 with the
same active owner: the renewal submitted at revision 6 had been accepted.
Cleanup then ended that owner at revision 8, with 42 ticks recorded. The POST
was not resent. This is an accepted renewal with a lost reply; it does not
establish why that reply was unavailable or whether the Vita slept. Increasing
the native connection budget alone has not eliminated transient lost replies.

A PC change now reconciles one uncertain renewal with a
single read-only status request. Continuation requires the exact expected next
revision, original owner, pinned build and power instance, and a session ceiling
that does not extend the original deadline; it never resends the POST. All 41
PC client tests and the actual C integration test passed. A fresh root rerun
passed all 41 native-lifecycle tests in 67.202 seconds, including bounded
rejection diagnostics. No native update or reboot is needed for that PC change.

At 22:06:55 UTC, a controlled live proxy deliberately dropped exactly one
accepted renewal reply. The keeper used one reconciliation GET to adopt the
same owner at the exact next revision, with the original session deadline
unchanged. Ticks advanced from 314 to 316. Exactly three POSTs were forwarded:
start, one renewal and end. One renewal was reconciled, no mutation was replayed,
no upstream failures were recorded, and end was confirmed. This qualifies that
controlled reply-loss case on the real Vita, not physical Wi-Fi interruption or
broad HTTP reliability. The private helper and original proof remain ignored;
the retained proof SHA-256 is
`58a2302d7ab5f79416cbaa1856c507b4e11f498eb05d5ddffee3f895963a8e1c`.
Broader live qualification remains incomplete.

Two subsequent holds remain retained failures. The first stopped after about
11 seconds on a diagnostic GET timeout, before any renewal; cleanup confirmed
end. The operator had used or moved the Vita, so it was not a controlled idle
trial. A later controlled hold stopped after about 22 seconds on a diagnostic
GET timeout, after three samples. The keeper stopped before submitting its
first renewal and cleanup again confirmed end. Diagnostic read timeouts are
transport failures; neither trial establishes a failure of the native power
tick or proves a sleep transition.

The isolated **120-second hold passed** at unchanged one-minute standby:
11 renewals, zero reconciliations, no keeper errors and a confirmed end at
21:42:53 UTC. It observed confirmed background renewal receipts without
additional diagnostic HTTP polling, using local `check(fresh=False)` checks.
This establishes bounded power and renewal continuity beyond the saved standby
timeout for that trial. It does not qualify diagnostic GET reliability or the
production checks before native effects. Production freshness checks remain unchanged.

A subsequent slow-transfer trial sent 4 KiB in 32 chunks of 128 bytes, spaced
1.1 seconds apart, taking about 35 seconds. The independent keeper completed
three renewals without errors and confirmed end at 21:43:37 UTC. The main upload
reply timed out under its five-second response deadline. It was not replayed.
At 21:48:23 UTC, read-only stat/hash inspection and a complete 4 KiB readback
confirmed publication and the exact expected payload, SHA-256
`c8f5d0341d54d951a71b136e6e2afcb14d11ed8489a7ae126a8fee0df6ecf193`.
The original upload's HTTP 201 reply remains unknown and its timeout remains
retained. This qualifies background renewal during that verified 35-second
transfer, without establishing broad HTTP reliability. The coordinator stopped
and **did not start the native cycle**.

A PC keeper-loss test then **passed**. The keeper process deliberately exited
with `os._exit` without ending its 30-second lease. At 21:47:42 UTC, read-only
status observed the same power instance inactive at revision 32 with reason
`lease_expired`. Two diagnostic GET timeouts were retained. This proves native
TTL expiry after PC process loss for that trial; it does not confirm physical sleep.

A separate native preview declined to proceed: `ready=false`, one occupied
application slot and guard result `-12004`. It made zero device mutations and
the execute tool was not called. This is an unstarted cycle, not a failed native
installation or launch. The operator has been asked to close all app cards.

After idle-shell readiness was established, a later native execution verified
all eight files in stage `14ee990ff41641eda253a9cef7a4f498`. It recorded ten
mutation submissions: create stage, eight file uploads and one install request.
The install request was rejected, no launch followed, and the keep-awake lease
ended with zero renewals and no keeper errors. That PC version retained only
`install_rejected`; its exact HTTP status and rejection reason are unavailable.
Read-only follow-up found Resident unblocked, idle-ready and without an active
operation; GET of the original operation returned 404, with no claim observed.

Source inspection confirms the existing ownership barrier: install ownership
receipts are scoped to the Resident build and are not migrated from 0.1.5 to
0.1.6. This is a likely explanation for the refusal, not a recovered runtime
reason. [The lifecycle guide](NATIVE-LIFECYCLE.md#resident-016-hardware-check)
records the constraint and proposed explicit adoption protocol.
The PC now preserves only whitelisted rejection status/reason/category fields;
all 41 native-lifecycle host tests passed, including six targeted real-HTTP tests.
The fresh root rerun passed in 67.202 seconds. This does not recover the old reply.

A subsequent install-diagnostic preparation stopped on its first preview GET
with `LifecycleTransport`, before a plan claim, journal, lease start or native
mutation. No new install was submitted, so the historical rejection's exact
cause remains unknown. The operator-facing result is a separate unstarted
preparation; its private no-mutation record is retained outside public evidence.


A separate launch-only probe at 21:58:05 UTC submitted launch
`fc9670653c214fc683bf6d3b4254687f` once and performed no installation. Runtime
PID `996399`, run `0b8c607779092318d6c4e38485832015`, passed all 25 self-test
samples with frames advancing from 14 to 620 and checksum `2727420034`.
Graceful exit was acknowledged at revision 2. The final absence check could not
pass its fresh keep-awake GET, which timed out while reading response headers.
The original overall result remains **unconfirmed** after one renewal; immediate
lease cleanup was also unconfirmed. No further effects were replayed.

Subsequent GET-only reconciliation at 22:01:48 UTC confirmed two stable
idle/closed-Lab observations and the same power instance inactive at revision 37
with reason `lease_expired`. It made zero device mutations and retained the
original job result. This establishes native launch, self-test, acknowledged
exit and later absence. It does not establish 0.1.6 installation,
redeployment or an uninterrupted keeper-protected native cycle.
Local receipt: `evidence/workbench/native-launch-only-20261012T215805Z-bf7f2d34/report.json`.
The public [validation record](resident-keep-awake-validation.json) summarizes it.

A separate launch-only probe at 22:07:25 UTC stopped on a `TimeoutError` before
starting a lease or submitting any native mutation. Its result remained blocked,
with the keeper reporting `not_started`; no launch or evaluation occurred. This
is a separate unstarted trial, not a successful repeat of the earlier probe.
Local receipt: `evidence/workbench/native-launch-only-20261012T220725Z-a8fa3025/report.json`.

Earlier post-end connection timeouts had no physical sleep confirmation for
those trials; network unavailability alone did not establish sleep. The operator
temporarily selected 30-minute standby for investigation and has now restored
the original one-minute setting.

A separate 0.1.6 **90-second hold passed** at the restored one-minute
setting: eight renewals, zero reconciliations, no keeper errors and confirmed
explicit end at 22:20:15 UTC. A subsequent GET-only observer requested 95 seconds
without renewing and recorded eight paired-port timeout observations. The
operator then directly confirmed, “Yes—it entered normal sleep,” and physically
woke the Vita to LiveArea. The subsequent lease begin confirmed the same Resident
build and power-worker instance. This qualifies normal automatic sleep after
explicit lease end on that 0.1.6 build. Physical sleep after TTL expiry,
full suspension and lease cancellation remain separate gates. The later Wi-Fi
trial below qualifies service recovery after manual reconnection only.

Local receipts:
`evidence/resident/keep-awake-hold-20261012T221842Z/proof.json`,
`evidence/resident/keep-awake-observe-20261012T222042Z/proof.json`, and
`evidence/resident/keep-awake-physical-sleep-20261012T222403Z/proof.json`.
The public [validation record](resident-keep-awake-validation.json) retains the
exact result, scope and receipt hashes.

A subsequent **90-second keeper-continuity trial passed**: seven renewals,
zero reconciliations, no errors and confirmed end at 22:26:42 UTC. During the
trial, the operator pressed Power, waited about ten seconds, then woke the Vita
with PS/Power and reported normal behavior. This is partial physical
button/display sleep-and-wake evidence. The keeper continued renewing, so full
suspension and lease cancellation during full suspension were not established.
Local receipt: `evidence/resident/keep-awake-hold-20261012T222511Z/proof.json`.
A later physical **Wi-Fi interruption trial initially had partial evidence**. After five successful
renewals through revision 65, the operator reported completing the requested
roughly 20-second Wi-Fi-off/on step. The keeper stopped when the next renewal's read-only
preflight timed out; neither that renewal POST nor an end POST followed, and
no operation was replayed. The original hold remains `failed_or_interrupted`.
After the operator reported reconnection and LiveArea, three power status GETs
and one main status GET timed out. At that initial readback, IP and awake-state
confirmation was pending; address change and one-minute standby were possible
confounds. Cancellation cause, timing and service recovery were unconfirmed.
No new lease, application operation or reboot was submitted during that readback.
Local receipts: `evidence/resident/keep-awake-hold-20261013T020247Z/proof.json`
and `evidence/resident/keep-awake-wifi-20261013T020450Z/qualification.json`.
The operator subsequently reported needing to reconnect Wi-Fi. After that manual
reconnection, **two GET-only observations passed**: both Resident services answered
on the same build and power-worker instance; the old lease was inactive with no
owner, revision 66 followed the last accepted revision 65, and tick count 559
stayed unchanged. This confirms service recovery and original-lease inactivity
without reboot or Starter. The retained reason was `listener_lost`; the first
cancellation cause and exact latency are not established by that single field.

A **separate fresh stdio MCP test passed** after the read-only recovery proof:
all 40 tools were discovered, begin/renew/end advanced revisions 67/68/69, and
post-end ticks stayed unchanged. The old interrupted job was not resumed or
replayed. Local receipts:
`evidence/resident/keep-awake-wifi-reconnected-20261013T021249Z/proof.json` and
`evidence/resident/keep-awake-tools-20261013T021339Z/proof.json`.
Autonomous Wi-Fi reassociation and repeated interruption reliability remain
unqualified; this bounded pass required the operator to reconnect the network.

Code review identified a response-budget edge: a lease POST can commit near the
end of its two-second connection budget, leaving no time to write its response
headers. This is a possible lost-reply path, not an established cause of the
periodic delays observed on hardware. The subsequent 0.1.7 phase instrumentation
and its first hardware result are recorded above; that failed GET had a complete
queued native reply.

The following results belong to the **previous 300 ms native-budget build**,
plugin SHA-256 `d8ca07cfb6ef6e367ed792b08f4bfe134053e609dfeb10a20c8845aff508c45a`,
build ID `ed4abe7bbf3f5cb6f52899d4bcace5483dd2fd19b193e7e6034fb1338ffd04d4`.
They remain historical evidence and do not qualify the currently installed build.

The subsequent planned 180-second hold with the operator's original
one-minute standby setting **failed after about 37 seconds**. A renewal POST
had an uncertain reply; the keeper stopped and did not replay it. The operator
later confirmed that the Vita had fully slept, but the time of sleep is unknown.
After a physical wake, readback retained the same power-worker instance and
showed revision 7, an inactive lease, 53 ticks, last tick at clock 163057 ms and
reason `listener_lost`. These observations do not establish whether sleep,
listener loss or the renewal interruption happened first, or why they happened.

A separate 120-second diagnostic hold **passed** with standby temporarily set
to 30 minutes by the operator: 33 samples, 11 renewals, no keeper errors and a
confirmed explicit end. This establishes transport and renewal continuity for
that trial; it cannot prove protection beyond the original one-minute standby
timeout.

After the operator restored the original one-minute standby setting, a separate
180-second repeat passed: 48 samples, 16 renewals, no keeper errors and a
confirmed end. That trial used the same earlier native build with updated
five-second PC timeout and diagnostics. It establishes bounded remote
availability beyond the saved standby timeout for that trial. It does not
identify the cause of the first uncertain renewal or qualify another native build.

A subsequent 95-second status-only observer did not renew a lease. It recorded
both service ports becoming unreachable about 25 seconds after the confirmed
end, followed by seven paired-port timeout observations. The operator then
confirmed full automatic sleep and physically woke the Vita into FTP. That
explicit-end sleep result is scoped to the previous build. It does not establish
a full configured standby interval starting at release, or qualify TTL expiry.

The next step is to correlate PC receive timing with the new native transport
phases, establish and fix the failure, then qualify
an uninterrupted keeper-protected native cycle. The launch-only runtime proof
and later absence observations do not qualify installation or redeployment. Cross-build ownership
adoption is queued future work, with pinned prior evidence and a distinct receipt;
it is not implemented and current permissions are unchanged.
The original standby setting was restored and normal automatic sleep after
explicit end passed under 0.1.6. The current setting is operator-confirmed
30-minute standby; 0.1.7 physical sleep remains unqualified.
Physical sleep after TTL expiry, full suspension and
lease cancellation still need qualification. Wi-Fi service recovery after manual
reconnection passed; autonomous reassociation and repeated interruption reliability
remain unqualified. Verified slow-transfer renewal and
keeper-loss native TTL expiry are completed evidence tiers; retained transport failures
remain evidence to investigate. CI at commit `5f18a25` passed with 32 hashed
artifact files; that result predates the subsequent PC reconciliation change.
Source commit `c7671385dc1b0c312c98f6d23715051e42c21856` is pushed with CI run
`38313311499` passed; it predates the new rejection-diagnostics patch.
CI run `38315537719` at commit
`74bbbc1317da279689ebdd27ba7498c48c5ed411` passed all 31 groups, with 32 artifact
files hash-verified. Later documentation and source-manifest refreshes require
separate exact-head validation.

## Ownership and expiry

Only the desktop administrator token can use the dedicated port **17869**.
Individual Companion credentials cannot inspect or change leases. Requests use
the same trusted LAN boundary as the existing Resident services, without TLS.

Each lease has a random job ID and lease ID, an exact Resident build pin and a
fresh power-worker instance ID. This instance is separate from the native
lifecycle instance. One job owns the lease at a time. Every accepted mutation
advances a revision; stale revisions, other owners and previous instances are
refused. A lease lasts **5–30 seconds** and can be renewed only until its original
**30-second–30-minute** session deadline. No lease is saved to disk or restored
at boot. Read-only status does not renew it.

The worker cancels protection on TTL or session expiry, network loss, a failed
power tick, clock regression or a worker gap over five seconds. The gap check is
a conservative interruption check. Power-button/display sleep and wake were
observed while renewal continued; full suspension and cancellation during it
still need hardware qualification. A lost mutation reply is never automatically replayed. Cleanup
may read the current status and end that same confirmed owner with its new
revision, or leave it to expire.

## What is protected automatically

The native lifecycle execute tool acquires a lease before device writes when
Resident advertises the 0.1.6-or-later capability, with a fixed thirty-minute job ceiling. It renews every ten seconds, checks
ownership before native effects and releases the lease in cleanup. Lost lease
confirmation stops further effects. Already submitted operations may still
need the existing read-only reconciliation workflow. Legacy 0.1.5 jobs retain
their previously qualified behavior without a keep-awake lease.

Status, preview and reconciliation calls do not acquire or renew a lease.
Control's older brightness/activity lease remains separate. Foreground Lua
sessions and other tools do not automatically acquire this Resident lease in
this first slice; use the explicit tools or a bounded PC command wrapper for
those workflows.

To protect a silent host build or another bounded command, from the checkout:

```powershell
.\.venv-devloop\Scripts\python.exe -m resident.keep_awake_client `
  --journal-dir .devloop-private\keep-awake-build --max-duration-ms 600000 `
  -- .\.venv-devloop\Scripts\python.exe tools/vita_app.py --help
```

Replace the command after `--` with the build command. The wrapper requires the
Vita awake, pins its endpoint, journals requests and receipts, and ends the lease
when the command exits. The command is stopped if lease confirmation is lost or
the overall deadline expires, including its owned compiler child processes.
Docker-daemon container jobs are outside that host process tree and require
their own execution bound. For long sessions start a new bounded job after
the previous job has ended, rather than extending its original deadline.

## MCP tools

Restart the PC Resident MCP connection after updating the checkout. The combined
source catalog contains **42 tools**, including these four lease tools and
two [0.1.7 transport diagnostic tools](RESIDENT-TRANSPORT.md). The installed
0.1.7 service implements both namespaces. Enabled-tool metadata enumerated all
42 names and direct registered status calls passed; metadata does not qualify
every runtime operation. The existing process's restart to load the PC deadline
correction remains pending.

| Tool | Behavior |
| --- | --- |
| `vita_resident_keep_awake_status` | Read owner, revision, remaining time and tick results |
| `vita_resident_keep_awake_begin` | Begin from an inactive, freshly pinned status |
| `vita_resident_keep_awake_renew` | Renew that exact owner and revision within its fixed deadline |
| `vita_resident_keep_awake_end` | Stop timer refresh for that exact owner and revision |

An explicit begin does not start a PC renewal thread. The calling workflow must
renew before TTL expires and end in cleanup. Prefer the job runner or command
wrapper for work that may remain silent for more than thirty seconds.

## Native implementation

A separate, bounded HTTP worker serves `GET /keep-awake/status` and
`POST /keep-awake/lease`. Bulk transfers on port 17866 cannot queue ahead of
lease renewals. The installed candidate gives each lease connection a two-second
total budget, with a five-second absolute PC HTTP deadline; the worker checks policy
while handling network I/O. Its build, host tests, exact runtime identity and
direct registered status checks and one corrected fresh-process 90-second
lease hold passed. The physical normal-boot gate, broad transport reliability
and current-build sleep remain unqualified.
Once per second, an active lease calls
`sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND)`.
It does not acquire a persistent power lock or refresh OLED dim/off timers.
The display may dim or turn off while the service remains online.

POST requires `Content-Type: application/octet-stream` and exactly 128 bytes,
little-endian `<8I32s32s32s`:

| Field | Value |
| --- | --- |
| magic / protocol | `0x31414b52` / `1` |
| expected revision | Current status revision |
| TTL milliseconds | `5000..30000`, or `0` to end |
| maximum duration milliseconds | `30000..1800000` on begin; `0` on renew/end |
| three reserved words | All zero |
| instance / lease / job IDs | Three 32-byte lowercase ASCII hexadecimal IDs |

The status reports the exact build and power instance, active owner, revision,
clock, lease/session time remaining, tick count/result and end reason.

## Qualification and update

Run `Build-Resident.ps1` for native packaging, exact source fingerprinting and
host tests. Pure policy tests cover ownership, replay, deadlines and failure
paths. Real C HTTP tests exercise authentication and framing. The real main
service integration deliberately stretches an upload beyond two short TTLs
while independent renewals and successful ticks advance, then verifies that
explicit end stops tick growth. PC tests cover heartbeat failure and cleanup.

Stage an immutable replacement using the existing Resident update procedure,
preserving the exact current plugin, pairing and config. Activation still needs
the operator to copy the staged config to **`ur0:tai/config.txt`** and reboot
normally. Neither withdrawn boot experiment is needed. The staged
`config.txt.before-update` restores the previous plugin if recovery is needed.

Live acceptance requires: normal boot with an inactive lease; online service
beyond the unchanged standby timeout during renewed work; renewal during a slow
main-service transfer; explicit end and eventual normal sleep; keeper process
loss and TTL expiry; and separate physical sleep/wake and Wi-Fi interruption
checks. Display behavior and remote availability are separate observations.
