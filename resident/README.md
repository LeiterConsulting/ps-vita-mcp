# Vita Resident

Resident 0.1.2 is installed on the test Vita. Startup and native pairing-window exchange passed; successful individual credential confirmation remains pending. The earlier 0.1.1 storage/runtime record is separate. Read the [pairing contract and manual gates](../docs/PAIRING.md) before deployment.

Background device status and verified DevLoop uploads through a SceShell user plugin. The combined desktop MCP bridge exposes 30 tools: four Resident, thirteen Control and thirteen Workbench tools.

The separately built 0.1.3 [native launch qualification candidate](../docs/RESIDENT-LAUNCH-CANDIDATE.md) adds retained native identity, immutable attempt storage, strict administrator-only broker HTTP and read-only app inventory. It is not installed. Launch remains disabled and unconditionally refused; no new boot entry or initialization-time launch is added. Hardware and foreground-policy qualification remain open.

Development resumed on October 11, 2026. The existing manual Starter path remains available. The separate [automatic startup helper](autostart/README.md) and boot diagnostic were withdrawn after October 12 boot failures; retain them disabled for offline investigation. [Autonomous preparation](../docs/AUTONOMOUS-DEVLOOP.md) separates the proven bounded Lua loop from native launch, installation and physical-input gates.

Start with the [complete functional MCP setup](../docs/GETTING-STARTED.md), [baseline acceptance](../docs/BASELINE.md) and [Control tool reference](../docs/CONTROL.md). Resident-specific activation and rollback are covered in [its guide](../docs/RESIDENT.md). Control Inspector's optional read-only checks are documented [here](../docs/INSPECTOR.md).
