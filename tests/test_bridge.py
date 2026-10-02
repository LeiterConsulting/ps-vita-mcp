"""Exercise the actual stdio MCP server against an explicitly simulated device."""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from PIL import Image, ImageDraw
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "0" * 32
state = {"revision": 1, "frame": 100, "sampled_ms": 1234, "protocol": 1, "app": "Vita DevLoop", "paused": True, "parameters": {"gravity": 620.0, "drag": .9, "brake": 10.0, "max_speed": 340.0}}
fault = {"stale": False, "drop_change": False, "bad_image": False}
calls = []

class Device(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, code, data, content_type="application/json", **headers):
        if not isinstance(data, bytes): data = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for key, value in headers.items(): self.send_header(key.replace("_", "-"), str(value))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self): self.process(False)
    def do_POST(self): self.process(True)
    def process(self, change):
        calls.append((self.command, self.path))
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.reply(401, {"error": "Pairing authorization required"}); return
        if fault["stale"]:
            self.reply(503, {"error": "Device sample is stale"}); return
        state["frame"] += 1
        if change:
            form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode(), strict_parsing=True)
            if int(form["expected_revision"][0]) != state["revision"]:
                self.reply(409, {"error": "Revision changed; read status before retrying"}); return
            state["revision"] += 1
            if self.path == "/parameters":
                for key, value in form.items():
                    if key != "expected_revision": state["parameters"][key] = float(value[0])
            else: state["paused"] = form["action"][0] == "pause"
            if fault["drop_change"]:
                self.close_connection = True; return
        if self.path == "/screenshot":
            image = Image.new("RGB", (1,1) if fault["bad_image"] else (960,544), (20,32,49))
            ImageDraw.Draw(image).text((20,20), "SIMULATED DEVICE - BRIDGE TEST", fill="white")
            data = io.BytesIO(); image.save(data, format="PNG")
            self.reply(200, data.getvalue(), "image/png", X_DevLoop_Revision=state["revision"], X_DevLoop_Frame=state["frame"], X_DevLoop_Sampled_Ms=state["sampled_ms"])
        elif self.path == "/input":
            self.reply(200, {**{k: state[k] for k in ("revision","frame","sampled_ms")}, "buttons": 0, "motion": {"read_result": 0, "acceleration": [0,0,1]}, "front": {"contacts": []}, "rear": {"contacts": []}})
        elif self.path == "/logs":
            self.reply(200, {**{k: state[k] for k in ("revision","frame","sampled_ms")}, "sequence": 1, "entries": [{"sequence": 1, "message": "Simulated device only"}]})
        else: self.reply(200, state)

def content(result):
    assert not result.isError, result
    return result.structuredContent or json.loads(result.content[0].text)

async def main():
    fixture_lines = (ROOT / "build/host/devloop-fixtures.jsonl").read_text().splitlines()
    fixtures = [json.loads(line) for line in fixture_lines]
    assert len(fixtures[1]["front"]["contacts"]) == 8 and len(fixtures[2]["entries"]) == 12
    print("PASS C sample JSON parses, including full touch arrays and escaped log ring")
    device = ThreadingHTTPServer(("127.0.0.1", 0), Device)
    thread = threading.Thread(target=device.serve_forever, daemon=True); thread.start()
    with tempfile.TemporaryDirectory(prefix="vita-devloop-test-") as folder:
        config = Path(folder) / "config.json"
        config.write_text(json.dumps({"host": "127.0.0.1", "port": device.server_port, "token": TOKEN}))
        environment = {**os.environ, "VITA_DEVLOOP_CONFIG": str(config)}
        parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / "bridge/server.py")], env=environment)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert {tool.name for tool in tools.tools} == {"vita_status", "vita_read_input", "vita_screenshot", "vita_get_logs", "vita_set_parameters", "vita_run_experiment", "vita_stage_package", "vita_script_status", "vita_load_script", "vita_script_control"}
                current = content(await session.call_tool("vita_status"))
                assert current["revision"] == 1 and current["paused"] and "bridge" in current
                assert "motion" in content(await session.call_tool("vita_read_input"))
                assert content(await session.call_tool("vita_get_logs"))["sequence"] == 1
                shot = await session.call_tool("vita_screenshot")
                assert not shot.isError and shot.structuredContent["width"] == 960
                image = next(item for item in shot.content if item.type == "image")
                assert Image.open(io.BytesIO(base64.b64decode(image.data))).size == (960,544)
                print("PASS actual MCP initialize, ten tool schemas, status/input/logs and PNG image content")
                current = content(await session.call_tool("vita_set_parameters", {"expected_revision": 1, "gravity": 900, "max_speed": 200}))
                assert current["revision"] == 2 and current["parameters"]["gravity"] == 900
                current = content(await session.call_tool("vita_run_experiment", {"action": "resume", "expected_revision": 2}))
                assert current["revision"] == 3 and not current["paused"]
                conflict = await session.call_tool("vita_set_parameters", {"expected_revision": 2, "gravity": 500})
                assert conflict.isError and state["parameters"]["gravity"] == 900
                before = len(calls)
                invalid = await session.call_tool("vita_set_parameters", {"expected_revision": 3, "gravity": 1501})
                assert invalid.isError and len(calls) == before
                print("PASS parameter/control commands, revision conflicts and local range validation")
                fault["stale"] = True
                assert (await session.call_tool("vita_status")).isError
                fault["stale"] = False
                config.write_text(json.dumps({"host": "127.0.0.1", "port": device.server_port, "token": "1"*32}))
                assert (await session.call_tool("vita_status")).isError
                config.write_text(json.dumps({"host": "127.0.0.1", "port": device.server_port, "token": TOKEN}))
                fault["bad_image"] = True
                assert (await session.call_tool("vita_screenshot")).isError
                fault["bad_image"] = False
                print("PASS stale, wrong-token and malformed screenshot responses remain errors")
                fault["drop_change"] = True; before = len(calls)
                ambiguous = await session.call_tool("vita_run_experiment", {"action": "pause", "expected_revision": 3})
                assert ambiguous.isError and len(calls) == before + 1 and state["revision"] == 4
                assert "outcome may be unknown" in ambiguous.content[0].text
                fault["drop_change"] = False
                assert content(await session.call_tool("vita_status"))["revision"] == 4
                device.shutdown(); device.server_close(); thread.join()
                assert (await session.call_tool("vita_status")).isError
                print("PASS dropped mutation response is not retried; reconnect state and offline errors are honest")
    print("6 bridge/protocol test groups passed using a simulated device; physical Wi-Fi acceptance remains separate.")

if __name__ == "__main__": asyncio.run(main())
