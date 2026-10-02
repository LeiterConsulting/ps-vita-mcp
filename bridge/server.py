"""Local stdio MCP bridge for the foreground Vita DevLoop application."""
from __future__ import annotations
import http.client
import hashlib
import io
import ipaddress
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from PIL import Image as PillowImage
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from ftp_staging import stage_package

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path(os.environ.get("VITA_DEVLOOP_CONFIG", str(ROOT / ".devloop-private/config.json")))
FTP_CONFIG = Path(os.environ.get("VITA_DEVLOOP_FTP_CONFIG", str(ROOT / ".devloop-private/ftp.json")))
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CHANGE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
mcp = FastMCP("Vita DevLoop", instructions="Experiment tools control the foreground Vita DevLoop app. Read status before a change; supply its revision. Never automatically retry a timed-out change. Screenshots show DevLoop's own display. DevLoop 01.02 supports live Lua source: read vita://scripting and the experiment resources, load code, inspect metrics, run and capture. Package staging independently uses the file manager's FTP server and leaves installation to the user. Never automatically replay a failed upload.", log_level="WARNING")

def configuration() -> dict:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        host = ipaddress.IPv4Address(config["host"])
        if not (host.is_private or host.is_loopback) or host.is_unspecified or host.is_multicast:
            raise ValueError("Use the Vita's local Wi-Fi IPv4 address")
        port = int(config.get("port", 17865))
        if not 1 <= port <= 65535 or not re.fullmatch(r"[0-9a-f]{32}", config["token"]):
            raise ValueError("Invalid pairing configuration")
        return {"host": str(host), "port": port, "token": config["token"]}
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError("Bridge is not configured. Run bridge/configure.py with the IPv4 address shown on Vita DevLoop.") from error

def request(path: str, fields: dict | None = None, *, source: bytes | None = None, script_headers: dict | None = None) -> tuple[bytes, dict, dict]:
    config = configuration()
    body = None if fields is None else "&".join(f"{key}={value}" for key, value in fields.items())
    if source is not None: body = source
    connection = http.client.HTTPConnection(config["host"], config["port"], timeout=7)
    started = time.monotonic()
    try:
        headers = {"Authorization": "Bearer " + config["token"], "Content-Type": "application/x-www-form-urlencoded", "Connection": "close"}
        if script_headers: headers.update(script_headers)
        connection.request("GET" if body is None else "POST", path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read(3 * 1024 * 1024 + 1)
        if len(data) > 3 * 1024 * 1024:
            raise RuntimeError("Device response exceeded the bridge limit")
        if response.status != 200:
            try:
                message = json.loads(data).get("error", "Request rejected")
            except (ValueError, AttributeError):
                message = "Request rejected"
            raise RuntimeError(f"Vita HTTP {response.status}: {str(message)[:200]}")
        return data, {key.lower(): value for key, value in response.getheaders()}, {"received_utc": datetime.now(timezone.utc).isoformat(), "round_trip_ms": round((time.monotonic() - started) * 1000, 2)}
    except (OSError, http.client.HTTPException) as error:
        suffix = " Change outcome may be unknown; read status before retrying." if body is not None else " Wake the Vita and open DevLoop."
        raise RuntimeError(f"Vita unavailable at {config['host']}:{config['port']}.{suffix}") from error
    finally:
        connection.close()

def json_request(path: str, fields: dict | None = None, **kwargs) -> dict:
    data, headers, timing = request(path, fields, **kwargs)
    if headers.get("content-type", "").split(";")[0] != "application/json":
        raise RuntimeError("Device returned an unexpected response type")
    result = json.loads(data)
    if not isinstance(result, dict) or any(type(result.get(key)) is not int or result[key] < 0 for key in ("revision", "frame", "sampled_ms")) or result["frame"] == 0:
        raise RuntimeError("Device returned an invalid or unsampled result")
    if path == "/status" and (result.get("protocol") != 1 or result.get("app") != "Vita DevLoop"):
        raise RuntimeError("Device protocol or application does not match")
    result["bridge"] = timing
    return result

def revision(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 0xffffffff:
        raise ValueError("expected_revision must be a positive uint32 from vita_status")
    return value

@mcp.tool(annotations=READ)
def vita_status() -> dict:
    """Read fresh experiment state, physics parameters, revision and frame number."""
    return json_request("/status")

@mcp.tool(annotations=READ)
def vita_read_input() -> dict:
    """Read actual buttons, analog sticks, front/rear touch and motion samples with device read results."""
    return json_request("/input")

@mcp.tool(annotations=READ)
def vita_get_logs() -> dict:
    """Read the last twelve experiment events and their sequence numbers."""
    return json_request("/logs")

@mcp.tool(annotations=READ)
def vita_screenshot() -> CallToolResult:
    """Capture DevLoop's own 960x544 display as PNG with its revision, frame and timestamp."""
    data, headers, timing = request("/screenshot")
    if headers.get("content-type", "").split(";")[0] != "image/png":
        raise RuntimeError("Device did not return a PNG screenshot")
    with PillowImage.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.size != (960, 544):
            raise RuntimeError("Invalid DevLoop screenshot dimensions or format")
        image.verify()
    metadata = {"revision": int(headers["x-devloop-revision"]), "frame": int(headers["x-devloop-frame"]), "sampled_ms": int(headers["x-devloop-sampled-ms"]), "width": 960, "height": 544, "bridge": timing}
    if metadata["frame"] <= 0 or metadata["revision"] <= 0 or metadata["sampled_ms"] < 0:
        raise RuntimeError("Invalid screenshot sample metadata")
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(metadata)), Image(data=data, format="png").to_image_content()], structuredContent=metadata)

@mcp.tool(annotations=CHANGE)
def vita_set_parameters(expected_revision: int, gravity: float | None = None, drag: float | None = None, brake: float | None = None, max_speed: float | None = None) -> dict:
    """Atomically change supplied physics values at a frame boundary. Ranges: gravity 50..1500 px/s^2, drag 0..8 /s, brake 1..30 /s, max_speed 50..500 px/s. Conflicting revisions fail without changing state."""
    fields = {"expected_revision": revision(expected_revision)}
    for name, value, low, high in (("gravity", gravity, 50, 1500), ("drag", drag, 0, 8), ("brake", brake, 1, 30), ("max_speed", max_speed, 50, 500)):
        if value is not None:
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be finite and within {low}..{high}")
            fields[name] = f"{value:.6f}"
    if len(fields) == 1:
        raise ValueError("Supply at least one physics parameter")
    return json_request("/parameters", fields)

@mcp.tool(annotations=CHANGE)
def vita_run_experiment(action: Literal["pause", "resume", "reset", "recenter", "stick", "tilt", "clear_obstacles"], expected_revision: int) -> dict:
    """Apply one experiment action at a frame boundary using the last observed revision. reset resets the ball, score and obstacles; recenter uses the current physical motion sample."""
    return json_request("/control", {"expected_revision": revision(expected_revision), "action": action})

@mcp.tool(annotations=CHANGE)
def vita_stage_package(expected_sha256: str) -> dict:
    """Stage only the current validated DevLoop VPK via file manager FTP. Supply its build-report SHA-256. Uses a fresh inbox directory, verifies two read-backs and returns the Vita path. Installation remains manual. Failed attempts are never retried or overwritten."""
    return stage_package(ROOT / "dist/devloop/vita_devloop.vpk", ROOT / "dist/devloop/build-report.json", FTP_CONFIG, expected_sha256)

@mcp.tool(annotations=READ)
def vita_script_status() -> dict:
    """Inspect the live Lua experiment's source hash, errors, metrics, memory, callback timing and rollback availability. Requires DevLoop 01.02 or newer."""
    return json_request("/script")

@mcp.tool(annotations=CHANGE)
def vita_load_script(name: str, source: str, expected_revision: int) -> dict:
    """Hot reload up to 16 KiB of Lua text into foreground DevLoop 01.02+. Script returns a table with update(dt,input), draw(), optional init(). See SCRIPTING.md for vita drawing/input/metric APIs. Hash verified on Vita; compile and preflight failures preserve the current script. Success starts paused and retains the previous VM for rollback."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
        raise ValueError("name must be 1..32 ASCII letters, digits, underscores or hyphens")
    encoded = source.encode("utf-8")
    if not 0 < len(encoded) <= 16384 or any(value < 32 and value not in (9, 10, 13) for value in encoded):
        raise ValueError("source must contain 1..16384 bytes of Lua text, without NUL or other binary controls")
    expected = hashlib.sha256(encoded).hexdigest()
    result = json_request("/script", source=encoded, script_headers={"Content-Type": "text/x-lua", "X-DevLoop-Revision": str(revision(expected_revision)), "X-DevLoop-Script-Name": name, "X-DevLoop-Script-SHA256": expected})
    if result.get("sha256") != expected or result.get("name") != name or result.get("source_bytes") != len(encoded) or not result.get("active") or not result.get("paused"):
        raise RuntimeError("Script acknowledgement did not match the uploaded source; inspect status before any retry")
    return result

@mcp.tool(annotations=CHANGE)
def vita_script_control(action: Literal["restart", "rollback", "native", "activate"], expected_revision: int) -> dict:
    """Restart Lua from its source, roll back to the previous healthy VM, switch to native Tilt Playground, or reactivate loaded Lua. Every successful change starts paused. Use vita_run_experiment pause/resume for execution."""
    device_action = "native" if action == "native" else "script_" + action
    return json_request("/control", {"expected_revision": revision(expected_revision), "action": device_action})

@mcp.resource("vita://scripting")
def scripting_reference() -> str:
    """Lua experiment API, edit/push/run workflow, limits and recovery."""
    return (ROOT / "SCRIPTING.md").read_text(encoding="utf-8")

@mcp.resource("vita://experiments/{name}")
def example_experiment(name: str) -> str:
    """Source for the shipped bounce and input_scope experiments."""
    if name not in ("bounce", "input_scope"):
        raise ValueError("Available examples: bounce, input_scope")
    return (ROOT / "experiments" / (name + ".lua")).read_text(encoding="utf-8")

if __name__ == "__main__":
    mcp.run(transport="stdio")
