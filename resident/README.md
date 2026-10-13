# Vita Resident

**As of October 13, 2026, Resident 0.1.7 is running with its exact build verified;
qualification is incomplete.** It provides a bounded keep-awake lease for active
development jobs.
The combined source catalog exposes 42 tools: thirteen Resident, thirteen Control
and sixteen Workbench. Leases do not change saved brightness or sleep settings.

Its two read-only diagnostic tools passed authorization, missing-record and
ring-preservation checks on hardware. Direct registered main, power and
diagnostic status calls passed; current enabled-tool metadata lists all 42
names. Metadata enumeration does not qualify every tool or confirm the existing
process loaded the PC correction; its restart is pending. Exact running identity does not confirm the physical
normal-boot gate. [Contract and qualification](../docs/RESIDENT-TRANSPORT.md).

A planned 90-second hold stopped after 36.44 seconds on a PC preflight GET
timeout, after two successful renewals. All 12 native replies were fully queued
and closed successfully, but queueing does not prove PC receipt or identify the
failure cause. Cleanup confirmed release; no application effects or mutation
replays occurred. A later direct registered record read also timed out.
Current-build broad transport reliability and physical sleep remain unqualified.
A second hold stopped after 85.01 seconds with six renewals and zero Python
reply bytes, despite complete native reply queueing; cleanup confirmed end.
Eight paired client/raw-socket GETs and four TCP-info GETs passed separately.
The timeout cause remains unknown.

The public PC deadline helper now applies the remaining five-second budget
before connect, send and every raw read. Its 75 focused client tests and six
private probe smoke cases passed. One instrumented fresh-process 90-second
hold then passed with eight renewals, no errors and confirmed end. All 22
connections returned bytes, with at most 3108.34 ms per connection. This is
one pass at 30-minute standby, not a delivery-cause fix, broad reliability,
physical sleep or native-cycle qualification. Native plugin bytes and no-replay
policy are unchanged.
[Current validation](../docs/resident-transport-validation.json).

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
after explicit end passed separately. Current standby is operator-confirmed at
30 minutes; those results do not qualify 0.1.7 physical sleep.
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
