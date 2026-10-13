# Vita Resident

**As of October 13, 2026, Resident 0.1.7 is running with its exact build verified.**
The current PC keeper passed a 90-second hold at one-minute standby with eight
renewals, confirmed end at revision 41 and tick count 377. After 75 quiet
seconds and one unreachable status GET, the operator confirmed usual normal
sleep before touching the Vita. This qualifies the bounded hold and sleep after
explicit release, separately from earlier retained failures.

Renewal-only preflight recovery is implemented: one eligible GET transport
timeout can trigger one guarded fresh GET before renewal. Original ownership,
revision, conservative TTL and session deadline remain pinned; POSTs are never
replayed. The current hold needed zero retries, so the retry path remains a
separate gate. Its localhost/in-memory controlled harness passed one withheld
GET, one retry, one renewal and exactly three forwarded POSTs with confirmed
end. The controlled Vita attempt stopped when its fresh upstream GET timed out:
no renewal POST, two begin/end POSTs and confirmed end at revision 43, tick 399.
The relay used a 4.5-second upstream budget versus the local five-second budget;
this limits comparison with the production deadline. Later unchecked/checked
Wi-Fi power-saving comparisons stopped on read-only baselines with zero POSTs.
The comparison is inconclusive; the original checked setting was physically
restored. Registered power and transport reads then passed on the same build
and instance, with the lease inactive at revision 43, tick 399. Recovery remains
unqualified.
[Recovery contract and evidence](../docs/RESIDENT-KEEP-AWAKE.md#renewal-preflight-recovery).

All 92 focused client tests passed (58 lease, eight deadline, 26 transport),
as did current host stdio, file-MCP and 41 native-lifecycle PC tests. Full CI for
this source is pending. CI at `caf5008` passed 33 groups and 34 verified artifact
files before renewal recovery was added. Native plugin bytes, saved settings
and the 42-tool catalog are unchanged. Restart the PC Resident MCP so registered
jobs load the new keeper; no Vita reboot is required.

Registered main/power/diagnostic reads and begin/renew/end passed after the
previous restart. Enabled metadata lists 42 names (13 Resident, 13 Control,
16 Workbench); this does not qualify every operation. Administrator rejection,
missing-record and ring-preservation checks passed separately. Broad transport
reliability, physical normal boot, TTL sleep, full-suspend cancellation and
current-build native installation/deployment remain unqualified. Earlier
native queued replies did not establish PC receipt or the timeout cause.
[Current validation](../docs/resident-transport-validation.json) and
[transport guide](../docs/RESIDENT-TRANSPORT.md).

The command wrapper protects one host command. Native execution starts its
keeper after local preparation and initial status; planning, build tooling and
Lua sessions do not automatically share a continuous lease. A future work
session needs explicit borrowing from one outer owner, avoiding nested keepers.
[Lease coverage](../docs/RESIDENT-KEEP-AWAKE.md#what-is-protected-automatically).

Historical **0.1.6** hardware passes cover fresh MCP lease operations, an isolated
120-second hold
at one-minute standby, renewal during a verified slow 4 KiB transfer, native
30-second expiry after PC keeper loss and one controlled lost-renewal reply
reconciled without replay. A separate launch-only probe passed self-test and
acknowledged graceful exit; later read-only checks confirmed closure. A separate
90-second hold ended cleanly, followed by operator-confirmed normal automatic sleep.

A physical Wi-Fi interruption stopped the PC keeper without replay. After the
operator manually reconnected Wi-Fi, both services responded on the same
build/instance: the old lease was inactive at revision 66, ownership cleared and
tick count 559 stable. Its retained `listener_lost` reason does not establish the
first cancellation cause or exact timing. Separate fresh stdio checks exposed
all 40 tools and passed lease status/begin/renew/end.

Intermittent HTTP timeouts remain a blocker: the launch-only job's original
result is unconfirmed, and current-build installation/redeployment and an
uninterrupted keeper-protected native cycle remain unqualified. The earlier
install rejection's exact runtime cause is unknown. Physical sleep after TTL
expiry, full suspension and lease cancellation, automatic Wi-Fi reassociation
and repeated Wi-Fi recovery remain unqualified. Power-button/display sleep and
wake worked while renewal continued; full suspension was not established.
One-minute standby was restored for those 0.1.6 trials, and automatic sleep
after explicit end passed separately. Earlier October 13 probes used 30-minute
standby; an earlier one-minute hold failed, while current source later passed
the bounded one-minute hold and explicit-release sleep under 0.1.7. TTL sleep and full-suspend
cancellation remain separate unqualified gates.
[Detailed evidence and pending gates](../docs/RESIDENT-KEEP-AWAKE.md) and
[dated validation record](../docs/resident-keep-awake-validation.json).

Accepted 0.1.5 and earlier rollback plugins are retained. Its five fixed-Lab
native cycles across two builds and same-build normal-reboot journal durability
are historical baseline evidence. The native namespace stages eight fixed files,
installs the owned Lifecycle Lab title and submits its fixed launch URI under a
conservative idle-shell policy. It performs no installation, launch or Promoter
initialization at boot. [Native lifecycle and ownership limits](../docs/NATIVE-LIFECYCLE.md).

[Managed inbox inspection](../docs/MANAGED-FILES.md) remains available: paginated listing, size/hash and bounded reads of final and retained partial files, without Control or FTP. Historical 0.1.4 inspection and upload results are recorded separately in the [managed-file validation record](../docs/managed-files-validation.json).

The [native launch qualification candidate](../docs/RESIDENT-LAUNCH-CANDIDATE.md), introduced in 0.1.3 and retained in 0.1.4, adds retained native identity, immutable attempt storage, strict administrator-only broker HTTP and read-only app inventory. Initial 0.1.4 broker flags `enabled`, `configured_enabled` and `blocked` were all false. That legacy DevLoop launch broker remains disabled and unconditionally refused; the fixed-Lab lifecycle namespace is separate. No new boot entry or initialization-time launch is added. Repeated boot, storage durability across reboot, phone confirmation and foreground/protected-UI launch policy remain open.

Development resumed on October 11, 2026. The existing manual Starter path remains available. The separate [automatic startup helper](autostart/README.md) and boot diagnostic were withdrawn after October 12 boot failures; retain them disabled for offline investigation. [Autonomous preparation](../docs/AUTONOMOUS-DEVLOOP.md) separates the proven bounded Lua loop from native launch, installation and physical-input gates.

Start with the [complete functional MCP setup](../docs/GETTING-STARTED.md), [baseline acceptance](../docs/BASELINE.md) and [Control tool reference](../docs/CONTROL.md). Resident-specific activation and rollback are covered in [its guide](../docs/RESIDENT.md). Control Inspector's optional read-only checks are documented [here](../docs/INSPECTOR.md).
