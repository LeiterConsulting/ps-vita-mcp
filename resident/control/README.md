# Vita Control 0.2.2 and Starter 01.00

The combined `resident/bridge.py` MCP server exposes four Resident tools and thirteen Control tools. Control adds background framebuffer readback, managed files, app commands, effective input observations and bounded synthetic input. Resident 0.1.1 remains the separate status/upload service.

- [Complete modded-Vita setup](../../docs/GETTING-STARTED.md)
- [Recorded functional baseline and new-device acceptance](../../docs/BASELINE.md)
- [Tool arguments, examples, preview and lifecycle](../../docs/CONTROL.md)
- [Recovery and troubleshooting](../../docs/TROUBLESHOOTING.md)

Build with `Build-Control.ps1` after checkout setup. It runs host C/MCP/FTP fixtures, builds and validates the matched native pair and Starter VPK, and writes exact source/package reports under `dist/control/`. It does not contact the Vita. Publication inputs and recorded device identities are documented separately.

Control loads only through the foreground Starter after a normal boot. CROSS starts one matched session; START+SELECT exits the Starter while Control remains loaded until reboot. Do not put the full Control pair in tai boot configuration. The earlier boot activation hung; the legacy `stage_control.py` CLI is disabled. Its functions remain for historical host fixtures.

`stage_starter.py` stages a fresh VPK after exact source/package/config/pairing checks and complete part/final readbacks. Installation is manual. After a confirmed normal reboot, `retire_session.py` can inspect and retain the exact stale Starter marker before another run. Never retire a marker to bypass an active session.

Input hooks derive from the MIT-licensed [vitacompanion kernel](https://github.com/devnoname120/vitacompanion/tree/d46772344d926e6765943703adf1a1518c20e10e/kernel); [its complete license](LICENSE.vitacompanion) is retained. No upstream FTP/command daemon, keep-awake behavior or USB driver is installed.
