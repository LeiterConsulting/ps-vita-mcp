"""Exercise the installed Vita through the real MCP stdio boundary; save bounded evidence."""
import argparse
import asyncio
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--change-proof", action="store_true", help="Exercise physics/run controls, then restore parameters and finish paused")
parser.add_argument("--causality-stress", type=int, default=0, help="Repeat pause/status pairs to check acknowledged revisions never regress (0..100)")
args = parser.parse_args()
if not 0 <= args.causality_stress <= 100: parser.error("--causality-stress must be within 0..100")

async def main():
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S-%f")
    folder = ROOT / "evidence/devloop" / ("live-" + stamp)
    folder.mkdir(parents=True)
    build = json.loads((ROOT / "dist/devloop/build-report.json").read_text())
    report = {"startedUtc": datetime.now(timezone.utc).isoformat(), "evidenceTier": "actual physical Vita accessed through MCP stdio", "package": build["package"], "steps": [], "physicalHumanInputAcceptance": "not inferred from these calls", "passed": False}
    async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(ROOT / "bridge/server.py")])) as (read, write):
        async with ClientSession(read, write) as session:
            try:
                await session.initialize()
                tools = await session.list_tools()
                names = [tool.name for tool in tools.tools]
                assert len(names) == 10 and "vita_load_script" in names
                report["tools"] = names
                watermark = {"revision": 0, "frame": 0}
                async def call(name, arguments=None):
                    result = await session.call_tool(name, arguments or {})
                    if result.isError: raise RuntimeError(result.content[0].text)
                    data = result.structuredContent or json.loads(result.content[0].text)
                    report["steps"].append({"tool": name, "arguments": arguments or {}, "result": data})
                    assert data["revision"] >= watermark["revision"], f"Revision regressed after acknowledgement: {watermark['revision']} -> {data['revision']}"
                    assert data["frame"] >= watermark["frame"], f"Frame regressed after acknowledgement: {watermark['frame']} -> {data['frame']}"
                    watermark.update({key: data[key] for key in watermark})
                    return data, result
                async def shot(label):
                    data, result = await call("vita_screenshot")
                    image = next(item for item in result.content if item.type == "image")
                    path = folder / (label + ".png")
                    pixels = base64.b64decode(image.data); path.write_bytes(pixels)
                    report["steps"][-1]["imageFile"] = path.name
                    report["steps"][-1]["imageSha256"] = hashlib.sha256(pixels).hexdigest()
                    print(f"Captured {label}: revision {data['revision']}, frame {data['frame']}")
                initial, _ = await call("vita_status")
                assert initial["app"] == "Vita DevLoop" and initial["version"] == build["package"]["version"]
                print(f"Connected to physical Vita DevLoop: revision {initial['revision']}, frame {initial['frame']}, {initial['fps']:.1f} sampled FPS")
                await call("vita_read_input"); await call("vita_get_logs"); await shot("initial")
                if args.change_proof:
                    async def control(action):
                        current, _ = await call("vita_status")
                        return await call("vita_run_experiment", {"action": action, "expected_revision": current["revision"]})
                    await control("pause")
                    current, _ = await call("vita_status")
                    changed, _ = await call("vita_set_parameters", {"expected_revision": current["revision"], "gravity": 1000, "drag": 2, "brake": 18, "max_speed": 220})
                    assert changed["parameters"] == {"gravity": 1000, "drag": 2, "brake": 18, "max_speed": 220}
                    observed, _ = await call("vita_status")
                    assert observed["parameters"] == changed["parameters"] and observed["frame"] > initial["frame"]
                    await shot("changed-physics")
                    await control("stick"); await control("reset"); await control("resume")
                    await asyncio.sleep(1)
                    await control("pause"); await control("recenter")
                    await control("clear_obstacles")
                    await control("stick" if initial["mode"] == "stick" else "tilt")
                    current, _ = await call("vita_status")
                    restored, _ = await call("vita_set_parameters", {"expected_revision": current["revision"], **initial["parameters"]})
                    assert restored["parameters"] == initial["parameters"] and restored["paused"]
                    await shot("restored-paused")
                    await call("vita_get_logs")
                    print("Live parameter/control proof passed; initial physics restored, experiment paused.")
                if args.causality_stress:
                    for _ in range(args.causality_stress):
                        current, _ = await call("vita_status")
                        changed, _ = await call("vita_run_experiment", {"action": "pause", "expected_revision": current["revision"]})
                        observed, _ = await call("vita_status")
                        assert observed["revision"] >= changed["revision"] and observed["frame"] >= changed["frame"]
                    report["causalityStressPairs"] = args.causality_stress
                    print(f"PASS {args.causality_stress} real-device command/status pairs without revision or frame regression.")
                report["passed"] = True
            except Exception as error:
                report["error"] = str(error)
                print("Live proof did not pass: " + str(error))
                print("Any acknowledged parameter changes may remain; inspect status before deciding another action.")
            finally:
                report["finishedUtc"] = datetime.now(timezone.utc).isoformat()
                (folder / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                print("Evidence: " + str(folder / "report.json"))
    return 0 if report["passed"] else 1

if __name__ == "__main__": sys.exit(asyncio.run(main()))
