# Resident keep-awake lease

As of October 12, 2026, the corrected **Resident 0.1.6 qualification candidate is
installed after a confirmed normal boot**. Its plugin SHA-256 is
`d8ca07cfb6ef6e367ed792b08f4bfe134053e609dfeb10a20c8845aff508c45a`
and its Resident build ID is
`ed4abe7bbf3f5cb6f52899d4bcace5483dd2fd19b193e7e6034fb1338ffd04d4`.
The accepted 0.1.5 is retained for rollback. One bounded three-minute online
trial has passed; physical sleep confirmation and broader qualification remain
pending. [The dated evidence record](resident-keep-awake-validation.json)
keeps host, packaging, API and physical results separate.

The lease is designed to keep an already awake Vita available while a bounded development
job runs. When the job finishes, loses its connection or stops renewing, Resident
stops refreshing the automatic suspend timer and allows the Vita's normal idle
policy to act. The timing depends on existing system timers; a full configured
interval starting at lease release has not been established.
No saved sleep setting, brightness, input state or boot configuration is changed
by a lease. An already suspended Vita still needs a physical wake.

## Interim hardware results

Fresh actual stdio MCP exposed all 40 tools and passed the four keep-awake
operations: status, begin, renew and end. The short trial started from an
inactive lease, observed successful ticks, ended the exact owner and observed
no tick growth afterward.

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
confirmed end. That trial used the same installed native build with updated
five-second PC timeout and diagnostics. It establishes bounded remote
availability beyond the saved standby timeout for that trial. It does not
identify the cause of the first uncertain renewal or qualify the next native
candidate.

A subsequent 95-second status-only observer did not renew a lease. It recorded
both service ports becoming unreachable about 25 seconds after the confirmed
end, followed by seven paired-port timeout observations. Physical confirmation
of full sleep is pending; network unavailability alone does not establish it.
The normal timer behavior after release remains unqualified.

The first uncertain renewal remains a retained failure to investigate. A slow
production-TTL upload, controlled expiry/end followed by confirmed normal sleep,
keeper process loss, manual sleep/wake, Wi-Fi loss and native lifecycle
execution with the new lease remain open hardware gates. A two-second native
connection-budget candidate has built successfully but is not installed. The
PC five-second absolute HTTP deadline passed 34 host tests and the actual C
integration rerun. Neither change inherits the installed build's trial results.

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
a conservative interruption check; manual sleep/wake needs hardware
qualification. A lost mutation reply is never automatically replayed. Cleanup
may read the current status and end that same confirmed owner with its new
revision, or leave it to expire.

## What is protected automatically

The native lifecycle execute tool acquires a lease before device writes when
Resident advertises the 0.1.6 capability, with a fixed thirty-minute job ceiling. It renews every ten seconds, checks
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
catalog contains **40 tools**, including these four additions:

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
lease renewals. Current candidate source gives each lease connection a two-second
total budget, with a five-second absolute PC HTTP deadline; the worker checks policy
while handling network I/O. The installed build identified above still uses
the earlier 300 ms native budget. The two-second candidate has passed its build
and host checks and needs separate activation and hardware qualification.
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
