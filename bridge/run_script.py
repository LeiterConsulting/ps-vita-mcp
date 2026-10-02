"""Explicit foreground edit/push/run loop through the real MCP client boundary."""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("file", type=Path)
parser.add_argument("--name")
parser.add_argument("--resume", action="store_true")
parser.add_argument("--capture", action="store_true")
parser.add_argument("--watch", action="store_true", help="Watch this file in the foreground until Ctrl+C")
args = parser.parse_args()
name = args.name or args.file.stem
if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name): parser.error("Supply a valid script name with --name")


def content(result):
    if result.isError: raise RuntimeError(result.content[0].text)
    return result.structuredContent or json.loads(result.content[0].text)


async def main():
    folder = ROOT / "evidence/devloop" / ("script-session-" + datetime.now().strftime("%Y-%m-%d_%H%M%S-%f"))
    folder.mkdir(parents=True)
    attempts = []
    last_seen = None
    environment={key:os.environ[key] for key in ("VITA_DEVLOOP_CONFIG","VITA_DEVLOOP_FTP_CONFIG") if key in os.environ}
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT / "bridge/server.py")],env=environment)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            while True:
                attempt = None
                try:
                    before = args.file.stat()
                    if before.st_size > 16384: raise ValueError("Script exceeds 16 KiB")
                    source = args.file.read_text(encoding="utf-8")
                    after = args.file.stat()
                    if before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
                        await asyncio.sleep(.35); continue
                    digest = hashlib.sha256(source.encode()).hexdigest()
                    if digest != last_seen:
                        last_seen = digest
                        attempt = {"utc": datetime.now(timezone.utc).isoformat(), "source_sha256": digest, "passed": False}
                        attempts.append(attempt)
                        current = content(await session.call_tool("vita_status"))
                        loaded = content(await session.call_tool("vita_load_script", {"name": name,"source": source,"expected_revision":current["revision"]}))
                        attempt["loaded"] = loaded
                        if args.resume:
                            attempt["resumed"] = content(await session.call_tool("vita_run_experiment", {"action":"resume","expected_revision":loaded["revision"]}))
                        if args.capture:
                            shot = await session.call_tool("vita_screenshot")
                            attempt["screenshot"] = content(shot)
                            image = next(item for item in shot.content if item.type == "image")
                            data = base64.b64decode(image.data)
                            filename = f"{len(attempts):03d}-{digest[:12]}.png"
                            (folder / filename).write_bytes(data)
                            attempt.update(image_file=filename,image_sha256=hashlib.sha256(data).hexdigest())
                        attempt["passed"] = True
                        print(f"Loaded {name}, {digest[:12]}, revision {loaded['revision']}; {'resume requested' if args.resume else 'paused'}",flush=True)
                except (OSError, UnicodeError, ValueError, RuntimeError) as error:
                    message = str(error)
                    if attempt is not None: attempt["error"] = message
                    elif last_seen == message:
                        await asyncio.sleep(.35); continue
                    else: last_seen = message
                    print("Edit not completed: " + message + "; no automatic retry of this content",flush=True)
                finally:
                    (folder / "report.json").write_text(json.dumps({"source_file":str(args.file.resolve()),"name":name,"attempts":attempts},indent=2)+"\n")
                if not args.watch:
                    print("Evidence: " + str(folder)); return 0 if attempts and attempts[-1]["passed"] else 1
                await asyncio.sleep(.35)


if __name__ == "__main__":
    try: sys.exit(asyncio.run(main()))
    except KeyboardInterrupt: print("Watch stopped; the Vita's last acknowledged experiment state is retained.")
