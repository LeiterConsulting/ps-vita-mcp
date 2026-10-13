# Background status and verified uploads

**As of October 13, 2026, Resident 0.1.7 is running with its exact build verified.**
The SceShell user plugin serves background status, a bounded upload inbox and
managed-file inspection on port **17866**. Port **17869** serves bounded
keep-awake leases and administrator-only transport diagnostics. The PC bridge
is `resident/bridge.py`; leases do not change saved sleep or brightness settings.

Current PC source passed a **90-second hold at one-minute standby**: eight
renewals, no retries, confirmed end at revision 41 and tick count 377. After
75 quiet seconds and one unreachable status GET, the operator confirmed normal
automatic sleep before touching the Vita. Network unavailability alone is not
proof of sleep. The earlier failed holds remain retained; this bounded pass
does not establish broad reliability or the intermittent delivery cause.

The keeper can make one additional GET after an eligible renewal-preflight
transport timeout, preserving ownership, original revision, local TTL and fixed
session deadline. POSTs are never replayed; native-effect freshness reads remain
strict. The current hold did not exercise that retry. A localhost/in-memory
controlled harness passed its one-withheld-GET case. The Vita attempt stopped
when the fresh upstream GET also timed out, sending no renewal POST and only
begin/end, with confirmed end at revision 43, tick 399. Its relay's 4.5-second
upstream budget was shorter than the local five-second budget; the recovery
remains unqualified. Later unchecked/checked Wi-Fi power-saving comparisons
stopped on read-only baselines with zero POSTs. The comparison is inconclusive;
the operator restored the original checked setting and reconnected Wi-Fi.
Registered power and transport reads passed on the same build and instance,
with the lease inactive at revision 43, tick 399. All 92 focused client tests and current host
stdio, file-MCP and 41 native-lifecycle PC tests passed.
[CI run 38456106601](https://github.com/LeiterConsulting/ps-vita-mcp/actions/runs/38456106601)
passed all 33 host groups at code commit `2a32d08`, with all 34 required artifact
files independently size/hash-verified. This later documentation-only checkpoint
preserves that PC and native code; CI ran on the named code commit.
Restart the PC MCP to load the new keeper into registered jobs.

Registered main/power/diagnostic status and record reads and begin/renew/end
passed after the previous restart. Enabled metadata lists 42 names; this is
separate from qualification of every tool. Authorization, missing-record and
ring-preservation checks passed on hardware. Native plugin bytes are unchanged.
Physical normal boot, TTL sleep, full-suspend cancellation and current-build
native installation/deployment remain unqualified.
[Current diagnostic validation](resident-transport-validation.json),
[transport guide](RESIDENT-TRANSPORT.md) and
[recovery contract](RESIDENT-KEEP-AWAKE.md#renewal-preflight-recovery).

The command wrapper protects one host command, and native execution starts its
keeper after local preparation and initial status. Planning, builds and Lua
sessions do not automatically share a work-session lease. Continuous coverage
needs future explicit borrowing from one outer owner, avoiding nested keepers.
[Current coverage](RESIDENT-KEEP-AWAKE.md#what-is-protected-automatically).

Historical **0.1.6** hardware passes cover fresh MCP lease operations, an isolated
120-second hold
at one-minute standby, renewal during a verified slow 4 KiB transfer, native
30-second expiry after PC keeper loss and one controlled lost-renewal reply
reconciled without replay. A launch-only probe passed self-test and acknowledged
exit, with later absence confirmed. A separate 90-second hold ended cleanly,
followed by operator-confirmed normal automatic sleep.

A physical Wi-Fi interruption stopped the PC keeper without replay. After the
operator manually reconnected Wi-Fi, both services responded on the same
build/instance: the old lease was inactive at revision 66, ownership cleared and
tick count 559 stable. Its retained `listener_lost` reason does not establish the
first cancellation cause or exact timing. Separate fresh stdio checks exposed
all 40 tools and passed lease status/begin/renew/end.

Intermittent HTTP timeouts still interrupt freshness checks, and the launch-only
job's original result remains unconfirmed. Current-build installation/redeployment
and an uninterrupted keeper-protected native cycle remain unqualified; the
historical install rejection's exact cause is unknown. Physical sleep after TTL
expiry, full suspension and lease cancellation, automatic Wi-Fi reassociation
and repeated Wi-Fi recovery remain unqualified. Power-button/display sleep and
wake worked while renewal continued; full suspension was not established.
One-minute standby was restored for those 0.1.6 trials, and automatic sleep after
explicit end passed separately. Earlier October 13 probes used 30-minute
standby; an earlier one-minute hold failed, while current source later passed
the bounded one-minute hold and explicit-release sleep under 0.1.7. TTL sleep and full-suspend
cancellation remain separate unqualified gates.
[Exact installed identity, detailed trials and pending gates](RESIDENT-KEEP-AWAKE.md)
and [dated validation record](resident-keep-awake-validation.json).

Accepted 0.1.5 and earlier rollback plugins are retained. The five 0.1.5 native
cycles across two builds and same-build reboot durability remain historical
baseline evidence. [Native lifecycle qualification](NATIVE-LIFECYCLE.md),
[managed-file qualification](managed-files-validation.json) and
[pairing gates](PAIRING.md) retain their separate acceptance records.

## Build

From the repository root, with Docker Desktop running:

```powershell
.\Setup-DevLoop.ps1
.\Build-Resident.ps1
```

The accepted predecessor is the corrected Resident 0.1.5 [native lifecycle candidate](NATIVE-LIFECYCLE.md), retained after normal-boot and exact-binary verification; five fixed-Lab install/launch/evaluate/graceful-exit cycles across two native builds passed on hardware, with same-build normal-reboot journal durability passed without replay, and accepted 0.1.4 is retained for rollback. The candidate adds owned Lifecycle Lab installation and fixed-title launching. The legacy DevLoop launch broker remains disabled. The historical 0.1.4 normal-boot and read-only inspection results above do not qualify the new build. The build runs the actual C HTTP/storage service under sanitizers with host adapters, MCP stdio fixtures, first-install FTP fixtures and update fixtures. It validates the ARM module's identity, imports, lifecycle, unresolved symbols and source fingerprint. Outputs are `dist/resident/vita_resident.suprx` and `dist/resident/build-report.json`. Building does not contact the Vita.

The combined public source bridge exposes thirteen Resident tools, thirteen [Control tools](CONTROL.md) and sixteen [Workbench tools](../workbench/README.md), for 42 total. Three native lifecycle tools require Resident 0.1.5 and target only the dedicated `VMCP00001` lab; retained 0.1.4 does not implement that namespace. Script-preparation/session tools run on the PC through the existing foreground DevLoop API; they do not add native capabilities to installed Resident. Three inspection tools introduced in 0.1.4 are documented in [Managed files](MANAGED-FILES.md): `vita_resident_list_inbox`, `vita_resident_file_info` and `vita_resident_read_file`. They inspect permitted inbox attempts and retained parts without changing files. Older supported versions, including the 0.1.3 rollback, do not implement them. The original Resident subset retains these four operations:

| Tool | Operation |
| --- | --- |
| `vita_resident_status` | Read heartbeat, service instance, battery, clocks and network state |
| `vita_resident_probe_upload` | Publish a fixed 4 KiB probe into a fresh inbox attempt |
| `vita_resident_stage_package` | Validate and publish the local DevLoop VPK using its exact SHA-256 |
| `vita_resident_verify_upload` | Read a named published package/probe twice and verify its length/hash |

Package uploads are limited to **8 MiB**. The service writes a fresh `.part`, verifies its stored hash and renames it to the final name. The bridge then performs two complete readbacks. A failed reply may leave a completed upload: verify its reported attempt before deciding what to do next. Uploads are never automatically replayed. DevLoop installation remains manual; the separate 0.1.5 native lifecycle candidate implements installation only for its fixed lab title, with five native Lab cycles across two builds passed and same-build normal-reboot journal durability passed without replay.

The earlier October 12 registered desktop MCP check exposed all 33 tools available at that point. Direct registered-tool calls verified exact installed 0.1.4 status, managed attempt listing, file size/SHA-256 and a complete 4096-byte read with independent full-file hash verification. DevLoop retained the same paused runtime identity and revision while frames advanced. Earlier fresh stdio checks remain separate evidence; the PC refresh did not reload the Vita plugin.

The October 12 refreshed registered MCP exposed all 36 tools and passed direct Resident 0.1.5 status, an unexecuted native preview and GET-only reconciliation of the completed post-reboot job. These checks added no native mutations. [Registered-client qualification](NATIVE-LIFECYCLE.md#registered-mcp-readiness-pass).

## Control-free scripts and launch candidate

An already open, healthy paused DevLoop 01.04 supports `vita_workbench_prepare_script_session` and `vita_workbench_script_session` without Control or a Resident launch broker. Exact native build/PID/run/revision pins bind up to eight hashed Lua candidates to that runtime. The runner measures finite metrics, ranks accepted candidates and restores the original paused VM between runs; explicit `retain_best` reloads the selected source fresh and paused. It has no work/input lease, power tick, keep-awake, capture or native installation. [Workbench workflow](../workbench/README.md#control-free-script-sessions).

The corrected default and explicit-retention two-candidate script proofs passed on the installed Vita on October 12, with stable exact identity and rate-based selection. Default restoration and separate guarded cleanup after retention restored the original paused scene/native world. The initial cumulative-distance ranking assertion failed due unequal execution times and is retained, along with a reconciled PC cleanup-journal failure. This proves foreground script iteration through the existing API, not a new native Resident capability or physical-control acceptance.

An earlier default two-candidate regression passed with Resident 0.1.3 running in the background: rates 60/120, faster candidate selected, original native world/mode/parameters/ball/score/obstacles restored paused, and exact DevLoop build/PID/run retained. Lua finished inactive with the last VM retained, the documented native-fallback limit. Resident kept its native instance with the broker disabled and unblocked. The separate 0.1.4 foreground inspection/upload check made no Lua changes; a new Lua regression, native DevLoop launching and sleep/reopen remain unqualified.

The separate [launch broker](../resident/launch_broker/README.md) and `resident/launch_client.py` were introduced in the disabled Resident 0.1.3 native qualification build and remain disabled in 0.1.4. Native identity, immutable attempt storage, strict HTTP namespace and read-only app inventory reuse the existing worker. Historical 0.1.3 samples matched the exact build, retained one instance and advanced native time, with `enabled`, `configured_enabled` and `blocked` all false. Initial inventory resolved the running file manager to an AppId/PID/title. Eight further observations matched inventory's `CHRS00003` PID to exact, stable paused DevLoop build/PID/run telemetry with unchanged revision and advancing frames; Resident retained its instance and advanced its clock. Foreground/protected-UI/submission flags stayed false. Initial 0.1.4 inspection retained one disabled, unblocked broker instance with advancing time; storage durability across reboot and foreground/protected-UI launch policy remain pending. Native submission through this legacy broker is unconditionally refused; accepted Resident 0.1.4 has no launch import, boot dispatch, enable file or additional boot plugin. The separate 0.1.5 candidate adds only the fixed Lifecycle Lab launch path, with five native Lab cycles across two builds passed and same-build normal-reboot journal durability passed without replay. DevLoop still needs to be opened manually.

The future launch branch defaults off, requires explicit `allow_launch` plus exact Resident build/instance pins, and submits at most one fixed `CHRS00003` attempt after durable journaling. Lost replies are inspected without replay. [The native hardware sequence](RESIDENT-LAUNCH-CANDIDATE.md) separates the passed initial boot/identity/transfer and DevLoop PID-correlation checks from pending storage durability across reboot, foreground-policy and launch qualification. Neither withdrawn boot experiment was used for this Resident replacement.

## Stage and activate

This prototype loads at boot. Coordinate availability for installation and recovery. Inspect the actual active taiHEN configuration first; the current staging tool supports `ur0:tai/config.txt` with no overriding `ux0:tai/config.txt`. Keep a copy of the original configuration. Use its SHA-256, not a value from someone else's device.

Open the Vita file manager's FTP server and configure its displayed endpoint:

```powershell
.\.venv-devloop\Scripts\python.exe bridge\configure_ftp.py <Vita-IPv4-address>:<FTP-port>
.\.venv-devloop\Scripts\python.exe resident\stage.py --expected-config-sha256 <active-config-sha256>
```

Staging preserves the active configuration and creates a fresh setup directory, pairing file, inbox, configuration proposal and rollback copy. Files receive temporary and final readback checks. The exact paths and hashes appear in the local deployment receipt under `evidence/resident/`.

To activate manually, copy the staged setup folder's **config.txt** into **ur0:tai/**, replacing the active file, then reboot normally. There is no Resident VPK/bubble. Keep its `config.txt.before-resident` backup and the staged plugin files. Startup diagnostics are saved to `ux0:data/vita-resident/startup.log` with a 2 KiB bound and no pairing token.

To roll back, restore that original configuration through the file manager and reboot normally. Do not hot-unload or refresh the plugin: if it supplied the shared network pool, that pool must survive until SceShell exits.

The stage command creates `.devloop-private/resident.json`. Configure an additional MCP stdio server using absolute checkout paths:

```json
{
  "mcpServers": {
    "vita-resident": {
      "command": "C:/path/to/ps-vita-mcp/.venv-devloop/Scripts/python.exe",
      "args": ["C:/path/to/ps-vita-mcp/resident/bridge.py"]
    }
  }
}
```

DevLoop and Resident have separate native services, ports and pairing configurations. Resident uses unencrypted HTTP on a trusted LAN. It does not change sleep settings; true sleep or network loss can make it unavailable. Heartbeat and requests are sequential, so an upload can delay status responses.

## Updates and live qualification

`resident/stage_update.py` replaces exactly one inspected Resident configuration entry in a proposal, preserving pairing and all other configuration bytes. Its `--expected-config-sha256` and `--old-plugin` arguments bind the update to the inspected state. Activation remains a manual config copy and normal reboot.

`resident/prove_device.py` performs live actions only when explicitly run. It can collect status continuity, publish a probe or stage DevLoop, and record a user-supplied foreground label. That label does not establish which application is on screen. A restarted service fails a continuity claim. Test physical responsiveness and wake recovery separately.

The combined desktop bridge also exposes Control for bounded synthetic input, cross-app framebuffer readback and managed files. [Control tools](CONTROL.md) and the [functional baseline](BASELINE.md) document the recorded results and limits. The Resident 0.1.5 [native lifecycle candidate](NATIVE-LIFECYCLE.md) implements native installation only for the owned Lifecycle Lab; five native Lab cycles across two builds passed, and same-build normal-reboot journal durability also passed without replay; extension to DevLoop remains pending. The manual Starter path remains available after a confirmed normal boot and inspected native state. The separate [one-shot startup experiment](../resident/autostart/README.md) and isolated boot diagnostic are withdrawn after boot failures; both remain disabled, and recovered Resident operation is verified. Their source/host results do not qualify a new boot attempt or replace Resident. [Autonomous DevLoop](AUTONOMOUS-DEVLOOP.md) explains script/input readiness and the recovery. For the complete manual Resident/Starter/DevLoop path, use [GETTING-STARTED.md](GETTING-STARTED.md).
