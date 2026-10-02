"""Call this checkout's MCP staging tool and save the physical transfer receipt."""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    build = json.loads((ROOT / "dist/devloop/build-report.json").read_text())["package"]
    report = {"started_utc": datetime.now(timezone.utc).isoformat(),
              "evidence_tier": "Actual file manager FTP through this checkout's MCP stdio",
              "package_sha256": build["sha256"], "passed": False}
    target = ROOT / "evidence/devloop" / ("ftp-live-" + datetime.now().strftime("%Y-%m-%d_%H%M%S-%f"))
    target.mkdir(parents=True)
    try:
        async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(ROOT / "bridge/server.py")])) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                report["tools"] = [tool.name for tool in tools]
                assert len(tools) == 10 and "vita_stage_package" in report["tools"]
                result = await session.call_tool("vita_stage_package", {"expected_sha256": build["sha256"]})
                if result.isError:
                    raise RuntimeError(result.content[0].text)
                receipt = result.structuredContent or json.loads(result.content[0].text)
                report["receipt"] = receipt
                assert receipt["sha256"] == receipt["observed_sha256"] == build["sha256"]
                assert receipt["bytes"] == build["bytes"] and receipt["version"] == build["version"]
                assert receipt["title_id"] == build["titleId"] and receipt["installation"] == "pending"
                assert receipt["read_back_checks"] == 2
                report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
    finally:
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        (target / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["passed"]:
        print("PASS physical FTP staging through this checkout's MCP, two SHA-256 read-backs")
        print("Vita path: " + report["receipt"]["vita_path"])
        print("Package: " + report["receipt"]["version"] + "; installation pending")
    else:
        print("FAIL " + report["error"])
    print("Report: " + str(target / "report.json"))
    return 0 if report["passed"] else 1


if __name__ == "__main__": sys.exit(asyncio.run(main()))
