"""Run actual MCP stdio tools against a simulated control device, including uncertain writes."""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[2]
TOKEN='c'*32
files={}; calls=[]; bad_frame=False; drop_reply=False; bad_read=False
status_version='0.2.2'

class Device(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,code,data,mime='application/json'):
        if not isinstance(data,bytes): data=json.dumps(data).encode()
        self.send_response(code); self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        calls.append(('GET',self.path))
        if self.headers.get('Authorization')!='Bearer '+TOKEN: return self.reply(401,{'error':'unauthorized'})
        if self.path=='/status': return self.reply(200,{'app':'Vita Control','abi':1,'version':status_version,'build_id':'1'*64,'lease_remaining_ms':0})
        if self.path.startswith('/screen/'):
            w,h=240,136; data=bytes([20,60,100])*(w*h)
            head=struct.pack('<6Ii5I2Q',0x31465256,1,1,999 if bad_frame else w,h,len(data),77,12,960,544,1,0,1000,21000)
            return self.reply(200,head+data,'application/x-vita-rgb')
        if self.path.startswith('/workspace/read/'):
            key=self.path.removeprefix('/workspace/read/')
            if key not in files: return self.reply(404,{})
            data=files[key]; return self.reply(200,b'bad' if bad_read else data,'application/octet-stream')
        if self.path.startswith('/workspace/stat/'):
            key=self.path.removeprefix('/workspace/stat/'); data=files[key]
            return self.reply(200,{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if self.path.startswith('/workspace/list/'): return self.reply(200,{'entries':[],'more':False})
        return self.reply(404,{})
    def do_POST(self):
        calls.append(('POST',self.path)); payload=self.rfile.read(int(self.headers.get('Content-Length',0)))
        if self.headers.get('Authorization')!='Bearer '+TOKEN: return self.reply(401,{'error':'unauthorized'})
        if self.path=='/input':
            values=struct.unpack('<13Ii',payload); assert values[2]<=1000 and values[-1]==77
            return self.reply(200,{'lease_remaining_ms':values[2],'lease_buttons':values[3]})
        if self.path=='/release': return self.reply(200,{'lease_remaining_ms':0})
        if self.path.startswith('/workspace/write/'):
            key=self.path.removeprefix('/workspace/write/'); assert hashlib.sha256(payload).hexdigest()==self.headers['X-SHA256'];files[key]=payload
            if drop_reply: self.close_connection=True; return
            return self.reply(201,{'attempt':key.split('/')[0],'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'storage_readback':True,'vita_path':'ux0:data/vita-control/workspace/'+key})
        if self.path.startswith('/workspace/delete/'):
            key=self.path.removeprefix('/workspace/delete/')
            if hashlib.sha256(files[key]).hexdigest()!=self.headers['X-SHA256']: return self.reply(409,{})
            del files[key]; return self.reply(200,{'removed':True})
        if self.path.startswith('/app/'): return self.reply(200,{'native_result':0,'runtime_observation':'pending'})
        return self.reply(404,{})

def value(result): return result.structuredContent or json.loads(result.content[0].text)

async def main():
    global bad_frame,drop_reply,bad_read,status_version
    server=ThreadingHTTPServer(('127.0.0.1',0),Device);threading.Thread(target=server.serve_forever,daemon=True).start();checks=[]
    try:
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/'pairing.json';config.write_text(json.dumps({'host':'127.0.0.1','port':17866,'token':TOKEN}))
            env={**os.environ,'VITA_RESIDENT_CONFIG':str(config),'VITA_CONTROL_PORT':str(server.server_port)}
            async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'resident/control/server.py')],env=env)) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();catalog=await session.list_tools();assert len(catalog.tools)==13; checks.append('thirteen-control-tools-listed')
                    result=await session.call_tool('vita_control_status',{});assert not result.isError and value(result)['app']=='Vita Control';checks.append('status-identity-through-MCP')
                    status_version='0.2.1';assert not (await session.call_tool('vita_control_status',{})).isError
                    status_version='0.2.0';assert (await session.call_tool('vita_control_status',{})).isError
                    status_version='0.2.2';checks.append('recognized-compatible-versions-only')
                    result=await session.call_tool('vita_control_screen',{});assert not result.isError and value(result)['target_pid']==77 and any(item.type=='image' for item in result.content); checks.append('screen-image-and-timing-through-MCP')
                    bad_frame=True;assert (await session.call_tool('vita_control_screen',{})).isError;bad_frame=False;checks.append('invalid-frame-refused')
                    before=len(calls)
                    for args in [{'target_pid':77,'buttons':['cross'],'ttl_ms':1001},{'target_pid':77,'buttons':['PS']},{'target_pid':77,'buttons':[],'front_touch':[1920,0]}]:
                        assert (await session.call_tool('vita_control_input',args)).isError
                    assert len(calls)==before;checks.append('invalid-input-refused-before-device-call')
                    result=await session.call_tool('vita_control_input',{'target_pid':77,'buttons':['cross'],'front_touch':[900,500]});assert not result.isError and value(result)['lease_buttons']==16384
                    assert not (await session.call_tool('vita_control_release',{})).isError;checks.append('input-and-release-through-MCP')
                    result=await session.call_tool('vita_control_write_text',{'name':'hello.lua','text':'return 42\n'});assert not result.isError;proof=value(result);assert proof['read_back_checks']==2;checks.append('fresh-file-and-two-readbacks')
                    result=await session.call_tool('vita_control_read_text',{'attempt':proof['attempt'],'name':'hello.lua','expected_sha256':proof['sha256']});assert not result.isError and value(result)['text']=='return 42\n';checks.append('verified-text-readback')
                    before=len(calls);assert (await session.call_tool('vita_control_publish_file',{'relative_file':'../private.txt','expected_sha256':'1'*64})).isError; assert len(calls)==before;checks.append('local-file-escape-refused')
                    result=await session.call_tool('vita_control_copy_file',{'attempt':proof['attempt'],'name':'hello.lua','expected_sha256':proof['sha256'],'new_name':'copy.lua'});assert not result.isError and value(result)['attempt']!=proof['attempt'];checks.append('verified-copy-retains-source')
                    bad_read=True; assert (await session.call_tool('vita_control_read_text',{'attempt':proof['attempt'],'name':'hello.lua','expected_sha256':proof['sha256']})).isError;bad_read=False;checks.append('corrupt-readback-refused')
                    result=await session.call_tool('vita_control_delete_file',{'attempt':proof['attempt'],'name':'hello.lua','expected_sha256':proof['sha256']});assert not result.isError and value(result)['removed'];checks.append('hash-guarded-remove')
                    drop_reply=True;before=len(calls);result=await session.call_tool('vita_control_write_text',{'name':'uncertain.lua','text':'return 0'});drop_reply=False
                    assert result.isError and TOKEN not in result.content[0].text and 'attempt ' in result.content[0].text
                    assert sum(m=='POST' for m,p in calls[before:])==1;checks.append('lost-write-reply-not-replayed-and-identity-retained')
                    assert not (await session.call_tool('vita_control_app',{'action':'launch','title_id':'CHRS00003'})).isError;checks.append('allowlisted-app-command-with-observation-pending')
                    before=len(calls)
                    result=await session.call_tool('vita_control_sequence',{'target_pid':77,'steps':[{'buttons':['cross'],'ttl_ms':16},{'buttons':['PS']}]})
                    assert result.isError and len(calls)==before;checks.append('whole-sequence-validated-before-first-input')
                    result=await session.call_tool('vita_control_sequence',{'target_pid':77,'steps':[{'buttons':['cross'],'ttl_ms':16}]})
                    assert not result.isError and value(result)['result']=='completed input requests and screen observations' and value(result)['final_release']['lease_remaining_ms']==0;checks.append('bounded-sequence-records-images-and-final-release')
        print(json.dumps({'fixture':'Actual stdio MCP; simulated control HTTP hardware','passed':len(checks),'checks':checks},indent=2))
    finally: server.shutdown();server.server_close()
if __name__=='__main__': asyncio.run(main())
