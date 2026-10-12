# Vita Resident 0.1.2 pairing candidate

Resident 0.1.2 is installed on the test Vita. Startup and native pairing-window exchange passed; successful individual credential confirmation remains pending. The earlier 0.1.1 storage/runtime record is separate. Read the [pairing contract and manual gates](../docs/PAIRING.md) before deployment.

Background device status and verified DevLoop uploads through a SceShell user plugin. The combined desktop MCP bridge exposes 28 tools: four Resident, thirteen Control and eleven Workbench tools.

Development resumed on October 11, 2026. The existing manual Starter path remains available. The separate [automatic startup helper](autostart/README.md) is a default-disabled one-shot experiment with its own build and device gates; it does not replace Resident or qualify persistent startup. [Autonomous preparation](../docs/AUTONOMOUS-DEVLOOP.md) separates Lua script readiness from verified foreground input readiness.

Start with the [complete functional MCP setup](../docs/GETTING-STARTED.md), [baseline acceptance](../docs/BASELINE.md) and [Control tool reference](../docs/CONTROL.md). Resident-specific activation and rollback are covered in [its guide](../docs/RESIDENT.md). Control Inspector's optional read-only checks are documented [here](../docs/INSPECTOR.md).
