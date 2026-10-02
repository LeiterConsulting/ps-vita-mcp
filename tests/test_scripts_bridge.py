"""Actual MCP transport against an explicitly simulated script-aware device."""
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "0" * 32
calls = []
fault = {"drop": False, "wrong_hash": False, "wrong_name": False, "unpaused": False}
state = {"protocol": 1, "app": "Vita DevLoop", "version": "01.02", "revision": 1,"frame": 100,"sampled_ms": 1234,"paused":True}
script = {"loaded":False,"active":False,"faulted":False,"name":"","sha256":"","source_bytes":0,"rollback_available":False,"metrics":{}}
previous = {}


class Device(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, code, result):
        data=json.dumps(result).encode(); self.send_response(code)
        self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(data)))
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        calls.append(("GET",self.path))
        if self.headers.get("Authorization") != "Bearer " + TOKEN: self.reply(401,{"error":"Wrong token"}); return
        state["frame"]+=1
        self.reply(200,{**state,**script} if self.path=="/script" else state)
    def do_POST(self):
        global previous
        data=self.rfile.read(int(self.headers["Content-Length"])); calls.append(("POST",self.path))
        if self.headers.get("Authorization") != "Bearer " + TOKEN: self.reply(401,{"error":"Wrong token"}); return
        if self.path=="/script":
            assert self.headers["Content-Type"]=="text/x-lua"
            assert self.headers["X-DevLoop-Script-SHA256"]==hashlib.sha256(data).hexdigest()
            expected=int(self.headers["X-DevLoop-Revision"])
            if expected!=state["revision"]: self.reply(409,{"error":"Revision changed"}); return
            if data==b"bad syntax": self.reply(422,{"error":"sample.lua:1: syntax error"}); return
            previous=dict(script) if script["loaded"] else {}
            script.update(loaded=True,active=True,faulted=False,name=self.headers["X-DevLoop-Script-Name"],sha256=hashlib.sha256(data).hexdigest(),source_bytes=len(data),rollback_available=bool(previous),metrics={"test":1})
            state["paused"]=True; state["revision"]+=1
            if fault["drop"]: self.close_connection=True; return
            result={**state,**script}
            if fault["wrong_hash"]: result["sha256"]="0"*64
            if fault["wrong_name"]: result["name"]="wrong"
            if fault["unpaused"]: result["paused"]=False
            self.reply(200,result); return
        form=parse_qs(data.decode()); expected=int(form["expected_revision"][0])
        if expected!=state["revision"]: self.reply(409,{"error":"Revision changed"}); return
        action=form["action"][0]
        if action=="script_rollback":
            if not previous: self.reply(409,{"error":"No rollback VM"}); return
            old=dict(script); script.clear(); script.update(previous); previous=old
        if action=="native": script["active"]=False
        if action=="script_activate": script["active"]=True
        state["paused"]=action!="resume"; state["revision"]+=1
        self.reply(200,{**state,**script} if action.startswith("script_") or action=="native" else state)


def content(result):
    assert not result.isError,result
    return result.structuredContent or json.loads(result.content[0].text)


async def main():
    fixture=json.loads((ROOT/"build/host/script-fixture.json").read_text())
    assert fixture["runtime"]=="Lua 5.4.9" and fixture["metrics"]["front"]==2
    device=ThreadingHTTPServer(("127.0.0.1",0),Device)
    thread=threading.Thread(target=device.serve_forever,daemon=True); thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="vita-script-mcp-") as folder:
            config=Path(folder)/"config.json"; config.write_text(json.dumps({"host":"127.0.0.1","port":device.server_port,"token":TOKEN}))
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/"bridge/server.py")],env={**os.environ,"VITA_DEVLOOP_CONFIG":str(config)})
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    tools=(await session.list_tools()).tools; assert len(tools)==10
                    load=next(tool for tool in tools if tool.name=="vita_load_script")
                    assert set(load.inputSchema["properties"])=={"name","source","expected_revision"}
                    assert not load.annotations.idempotentHint
                    docs=await session.read_resource("vita://scripting"); assert "16,384" in docs.contents[0].text
                    example=await session.read_resource("vita://experiments/bounce"); assert example.contents[0].text==(ROOT/"experiments/bounce.lua").read_text()
                    try: await session.read_resource("vita://experiments/../private")
                    except Exception: pass
                    else: raise AssertionError("Unknown resource name accepted")
                    print("PASS actual MCP ten-tool schemas, scripting reference and bounded example resources")
                    source="return {update=function() end,draw=function() end} -- UTF8: café\n"
                    valid_source=source
                    result=content(await session.call_tool("vita_load_script",{"name":"sample","source":source,"expected_revision":1}))
                    assert result["sha256"]==hashlib.sha256(source.encode()).hexdigest() and result["source_bytes"]==len(source.encode()) and result["paused"]
                    result=content(await session.call_tool("vita_script_status")); assert result["metrics"]=={"test":1}
                    print("PASS exact UTF-8 source bytes, hash/header transport, paused acknowledgement and custom metrics")
                    before=len(calls)
                    for name, source in (("../bad","ok"),("bad\r\nHeader","ok"),("sample",""),("sample","x"*16385),("sample","a\0b"),("sample","\x1bLua")):
                        result=await session.call_tool("vita_load_script",{"name":name,"source":source,"expected_revision":2}); assert result.isError
                    assert len(calls)==before
                    assert (await session.call_tool("vita_load_script",{"name":"sample","source":"ok","expected_revision":0})).isError
                    assert len(calls)==before
                    print("PASS invalid names, binary/oversize source and revision are rejected before network calls")
                    assert (await session.call_tool("vita_load_script",{"name":"bad","source":"bad syntax","expected_revision":2})).isError
                    assert script["name"]=="sample" and state["revision"]==2
                    assert (await session.call_tool("vita_load_script",{"name":"old","source":"ok","expected_revision":1})).isError
                    print("PASS rejected syntax and revision conflicts leave the simulated current script intact")
                    for key in ("wrong_hash","wrong_name","unpaused"):
                        fault[key]=True
                        result=await session.call_tool("vita_load_script",{"name":"sample","source":valid_source,"expected_revision":state["revision"]})
                        assert result.isError and "acknowledgement" in result.content[0].text
                        fault[key]=False
                    print("PASS mismatched hash/name and unpaused upload acknowledgements are not accepted")
                    fault["drop"]=True; before=len(calls)
                    result=await session.call_tool("vita_load_script",{"name":"sample","source":valid_source,"expected_revision":state["revision"]})
                    assert result.isError and "outcome may be unknown" in result.content[0].text and len(calls)==before+1
                    fault["drop"]=False
                    for action in ("restart","rollback","native","activate"):
                        result=content(await session.call_tool("vita_script_control",{"action":action,"expected_revision":state["revision"]}))
                        assert result["paused"] and result["active"]==(action!="native")
                    print("PASS dropped upload is not retried; all four script controls use revision-guarded MCP transport")
                    source_file=Path(folder)/"cli.lua"; source_file.write_text(valid_source,encoding="utf-8")
                    process=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/"bridge/run_script.py"),str(source_file),"--resume",env={**os.environ,"VITA_DEVLOOP_CONFIG":str(config)},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                    output,errors=await asyncio.wait_for(process.communicate(),timeout=15)
                    assert process.returncode==0 and b"Loaded cli" in output, output+errors
                    assert script["name"]=="cli" and not state["paused"]
                    print("PASS foreground run_script CLI loads a file and resumes through MCP, with a saved receipt")
    finally: device.shutdown(); device.server_close(); thread.join()
    print("7 script MCP test groups passed against an explicit simulated device; native Lua/HTTP and physical acceptance are separate.")


if __name__=="__main__": asyncio.run(main())
