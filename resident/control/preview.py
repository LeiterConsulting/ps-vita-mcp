"""Local-only screen/input panel. Reads paired credentials on the PC, never sends them to the page."""
import argparse
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from bridge import configuration
from control.bridge_tools import ControlClient
from workbench.power import lease as work_lease
from workbench.session import exclusive

HTML='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vita Control</title>
<style>body{font:16px system-ui;background:#101921;color:#e6edf3;max-width:980px;margin:32px auto;padding:0 20px}h1{font-size:26px}button{background:#243746;border:1px solid #456578;color:inherit;border-radius:8px;padding:12px 18px;margin:4px;cursor:pointer}button:hover{background:#315368}#screen{width:100%;max-width:960px;image-rendering:auto;border-radius:10px;background:#070c10;aspect-ratio:960/544;height:auto;object-fit:contain}#status{color:#b0c5d5;min-height:24px}#error{color:#ffb0a5}section{margin:18px 0}.row{display:flex;flex-wrap:wrap;align-items:center;gap:6px}small{color:#a4b9c8}#details{font-size:13px}</style>
<h1>Vita Control</h1><p>Live view and short, automatically released inputs.</p><p><small>Live view keeps the display awake. After 30 seconds without device input or motion, it dims to 20% of its brightness. Pausing ends this temporary work lease.</small></p>
<section class="row"><button id="live">Start live view</button><button id="snap">Snapshot</button><button id="release">Release all input</button><select id="quality"><option value="false">Fast preview</option><option value="true">More detail</option></select></section>
<img id="screen" alt="Vita screen"><p id="status">Waiting for a snapshot.</p><p id="error"></p>
<section class="row" id="buttons"></section><section class="row"><button data-app="launch/CHRS00003">Open DevLoop</button><button data-app="launch/CHRS00009">Open Quake</button><button data-app="quit/CHRS00003">Close DevLoop</button><button data-app="quit/CHRS00009">Close Quake</button></section>
<small>Click the image for a front-panel touch. Buttons and touches last 250 ms. A changed screen process rejects stale input.</small><p id="details"></p>
<script>
let live=false,busy=false,pid=null,timer=null,received=0,renewed=0;
const el=id=>document.getElementById(id);
async function api(path,body){let r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let j=await r.json();if(!r.ok)throw Error(j.error||'Vita operation failed');return j}
async function snapshot(){if(busy)return;busy=true;try{if(live&&!document.hidden&&Date.now()-renewed>=10000){await api('/work',{ttl_ms:30000});renewed=Date.now()}let j=await api('/frame?detail='+el('quality').value);pid=j.metadata.target_pid;el('screen').src='data:image/png;base64,'+j.png;received=Date.now();el('error').textContent='';el('details').textContent='Frame '+j.metadata.sequence+' · Capture '+j.metadata.capture_ms+' ms · Round trip '+j.metadata.bridge.round_trip_ms+' ms'}catch(e){el('error').textContent=e.message;pid=null;pause()}finally{busy=false;if(live)timer=setTimeout(snapshot,750)}}
function pause(){live=false;renewed=0;clearTimeout(timer);el('live').textContent='Start live view';navigator.sendBeacon('/work',new Blob([JSON.stringify({ttl_ms:0})],{type:'application/json'}))}
async function input(values){try{if(pid===null)throw Error('Take a snapshot first.');await api('/input',{target_pid:pid,buttons:[],ttl_ms:250,...values});setTimeout(snapshot,300)}catch(e){el('error').textContent=e.message}}
for(let name of ['up','down','left','right','cross','circle','square','triangle','l','r','start','select']){let b=document.createElement('button');b.textContent=name[0].toUpperCase()+name.slice(1);b.onclick=()=>input({buttons:[name]});el('buttons').appendChild(b)}
el('snap').onclick=snapshot;el('live').onclick=()=>{if(live)pause();else{live=true;renewed=0;el('live').textContent='Pause live view';snapshot()}};
el('release').onclick=async()=>{try{await api('/release',{});el('error').textContent=''}catch(e){el('error').textContent=e.message}};
el('screen').onclick=e=>{let r=e.target.getBoundingClientRect();input({front_touch:[Math.min(1919,Math.max(0,Math.floor((e.clientX-r.left)/r.width*1920))),Math.min(1087,Math.max(0,Math.floor((e.clientY-r.top)/r.height*1088)))]})};
document.querySelectorAll('[data-app]').forEach(b=>b.onclick=async()=>{try{await api('/app',{operation:b.dataset.app});pid=null;setTimeout(snapshot,1000)}catch(e){el('error').textContent=e.message}});
setInterval(()=>el('status').textContent=received?'Last image received '+((Date.now()-received)/1000).toFixed(1)+' seconds ago.':'Waiting for a snapshot.',250);
document.addEventListener('visibilitychange',()=>{if(document.hidden)pause()});window.addEventListener('pagehide',pause);
</script>'''

def serve(port):
    client=ControlClient(configuration)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self,status,data,mime='application/json'):
            if not isinstance(data,bytes): data=json.dumps(data).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if self.path=='/': return self.reply(200,HTML.encode(),'text/html; charset=utf-8')
            if self.path in ('/frame?detail=false','/frame?detail=true'):
                try:
                    png,metadata=client.capture(self.path.endswith('true'));return self.reply(200,{'png':base64.b64encode(png).decode(),'metadata':metadata})
                except Exception: return self.reply(503,{'error':'Vita screen unavailable. Check that the Vita is awake and the control plugin is active.'})
            return self.reply(404,{})
        def do_POST(self):
            origin=self.headers.get('Origin');expected='http://127.0.0.1:'+str(self.server.server_port)
            if origin!=expected or self.headers.get('Content-Type')!='application/json': return self.reply(403,{})
            try:
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=4096: raise ValueError()
                value=json.loads(self.rfile.read(length))
                if self.path=='/input': result=client.input(**value)
                elif self.path=='/release': result=client.release()
                elif self.path=='/work':
                    with exclusive():result=work_lease(client,**value)
                elif self.path=='/app' and value.get('operation') in ('launch/CHRS00003','launch/CHRS00009','quit/CHRS00003','quit/CHRS00009'): result=client.json('POST','/app/'+value['operation'],b'')
                else: raise ValueError()
                return self.reply(200,result)
            except Exception: return self.reply(400,{'error':'Operation rejected. Refresh the screen before trying a new input.'})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(json.dumps({'url':'http://127.0.0.1:'+str(server.server_port),'credentials_in_browser':False}),flush=True)
    try: server.serve_forever()
    finally: server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=0);serve(parser.parse_args().port)
