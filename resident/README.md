# Vita Resident

**Resident 0.1.6 is installed after a confirmed normal boot; qualification is
incomplete.** It adds a bounded keep-awake lease for active development jobs.
The combined source catalog exposes 40 tools: eleven Resident, thirteen Control
and sixteen Workbench. Leases do not change saved brightness or sleep settings.

Hardware passes cover fresh MCP lease operations, an isolated 120-second hold
at one-minute standby, renewal during a verified slow 4 KiB transfer, native
30-second expiry after PC keeper loss and one controlled lost-renewal reply
reconciled without replay. A separate launch-only probe passed self-test and
acknowledged graceful exit; later read-only checks confirmed closure. A separate
90-second hold ended cleanly, followed by operator-confirmed normal automatic sleep.

Intermittent HTTP timeouts remain a blocker: the launch-only job's original
result is unconfirmed, and current-build installation/redeployment and an
uninterrupted keeper-protected native cycle remain unqualified. The earlier
install rejection's exact runtime cause is unknown. Physical sleep after TTL
expiry, full suspension and lease cancellation, and real Wi-Fi interruption remain
pending. Power-button/display sleep and wake worked while renewal continued;
full suspension was not established. One-minute standby is restored, and automatic
sleep after explicit end passed separately.
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
