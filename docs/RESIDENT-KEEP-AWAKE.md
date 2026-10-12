# Resident keep-awake lease

As of October 12, 2026, Resident **0.1.6 is a qualification candidate**.
The installed, accepted 0.1.5 remains the rollback. Build and host tests do not
establish that the Vita stays online or returns to sleep; live results are
recorded separately in `resident-keep-awake-validation.json`.

The lease keeps an already awake Vita available while a bounded development
job runs. When the job finishes, loses its connection or stops renewing, Resident
stops refreshing the automatic suspend timer. The Vita can then sleep after its
normal configured idle interval. The previous timer remainder is not restored.
No saved sleep setting, brightness, input state or boot configuration is changed
by a lease. An already suspended Vita still needs a physical wake.

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
the overall deadline expires. For long sessions start a new bounded job after
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
lease renewals. Each lease connection has a 300 ms total budget, and the worker
checks policy while handling network I/O. Once per second, an active lease calls
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
