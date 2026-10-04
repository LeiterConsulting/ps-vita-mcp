"""Register bounded control, screen and workspace tools on the resident MCP server."""
from datetime import datetime, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import struct
import time
from typing import Literal
import uuid
import sys
from PIL import Image as PILImage
from mcp.server.fastmcp import Image
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from .rgb_codec import decode_rle
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from workbench.session import serialized

MAX_FILE=8*1024*1024
FRAME=struct.Struct('<6Ii5I2Q')
BUTTONS={'select':1,'start':8,'up':16,'right':32,'down':64,'left':128,'l':256,'r':512,'triangle':4096,'circle':8192,'cross':16384,'square':32768}
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=False,openWorldHint=False)
REMOVE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,idempotentHint=False,openWorldHint=False)


class ControlClient:
    def __init__(self,configuration): self.configuration=configuration; self.abi=None; self.codecs=[];self.power_protocol=None;self.work_renewed=0
    @serialized
    def request(self,method,path,body=None,digest=None,limit=8192):
        # Work keeps an awake display alive; status/power inspection alone does not.
        if path!='/status' and not path.startswith('/power/'):
            if self.abi is None:self.status()
            if self.power_protocol==1 and time.monotonic()-self.work_renewed>=10:
                raw,mime,_=self._wire('POST','/power/lease',struct.pack('<5I',0x31505756,2,30000,30000,20))
                work=json.loads(raw)
                if mime!='application/json' or work.get('app')!='Vita Work Power' or work.get('abi')!=2 or type(work.get('lease_remaining_ms')) is not int or not 0<work['lease_remaining_ms']<=30000:
                    raise RuntimeError('Work lease receipt differs; requested operation was not submitted')
                self.work_renewed=time.monotonic()
        return self._wire(method,path,body,digest,limit)
    def _wire(self,method,path,body=None,digest=None,limit=8192):
        config=self.configuration()
        port=int(os.environ.get('VITA_CONTROL_PORT',config['port']+1))
        if not 1<=port<=65535: raise ValueError('Invalid control port')
        connection=http.client.HTTPConnection(config['host'],port,timeout=10 if body is None else 30)
        headers={'Authorization':'Bearer '+config['token'],'Connection':'close'}
        if digest: headers['X-SHA256']=digest
        started=time.monotonic()
        try:
            connection.request(method,path,body,headers); response=connection.getresponse(); data=response.read(limit+1)
            if len(data)>limit: raise RuntimeError('Control response exceeds its bound')
            if response.status not in (200,201): raise RuntimeError(f'Control operation rejected with HTTP {response.status}; inspect state before repeating a mutation')
            return data,response.getheader('Content-Type','').split(';')[0],{'received_utc':datetime.now(timezone.utc).isoformat(),'round_trip_ms':round((time.monotonic()-started)*1000,2)}
        except (OSError,http.client.HTTPException) as error:
            raise RuntimeError('Control connection unavailable or interrupted; input expires automatically, file mutations must not be replayed') from error
        finally: connection.close()
    def json(self,method,path,body=None,digest=None):
        data,mime,timing=self.request(method,path,body,digest)
        if mime!='application/json': raise RuntimeError('Unexpected control reply format')
        result=json.loads(data)
        if not isinstance(result,dict): raise RuntimeError('Unexpected control reply')
        return {**result,'bridge':timing}
    def status(self):
        value=self.json('GET','/status')
        if value.get('app')!='Vita Control' or (value.get('version'),value.get('abi')) not in (('0.2.1',1),('0.2.2',1),('0.3.0',2),('0.3.1',2),('0.3.2',2),('0.3.3',2)) or not re.fullmatch('[0-9a-f]{64}',value.get('build_id','')):
            raise RuntimeError('Unexpected control endpoint identity')
        self.abi=value['abi']; self.codecs=value.get('capture_codecs',[]);self.power_protocol=value.get('power_protocol')
        return value
    def capture(self,detail=False):
        if self.abi is None: self.status()
        compressed=self.abi==2 and 'rle' in self.codecs
        body,mime,timing=self.request('GET','/screen/'+('detail' if detail else 'preview')+('/rle' if compressed else ''),limit=76+480*272*3+1020)
        if mime!=('application/x-vita-rgb-rle' if compressed else 'application/x-vita-rgb') or len(body)<64: raise RuntimeError('Unexpected framebuffer format')
        magic,abi,seq,w,h,size,pid,vblank,sw,sh,flags,reserved,start,end=FRAME.unpack(body[:64])
        if magic!=0x31465256 or abi!=self.abi or not 0<w<=480 or not 0<h<=272 or size!=w*h*3 or pid<=0 or sw>960 or sh>544 or sw<w or sh<h or end<start or flags!=1 or reserved!=0:
            raise RuntimeError('Invalid framebuffer dimensions, process or timestamps')
        encoding_us=0
        if compressed:
            if len(body)<76: raise RuntimeError('Missing frame codec header')
            tag,encoded_size,encoding_us=struct.unpack('<3I',body[64:76])
            if tag!=0x31454c52 or encoded_size!=len(body)-76: raise RuntimeError('Invalid frame codec header')
            rgb=decode_rle(body[76:],size)
        else:
            if len(body)!=64+size: raise RuntimeError('Invalid raw frame length')
            rgb=body[64:]
        output=io.BytesIO(); PILImage.frombytes('RGB',(w,h),rgb).save(output,format='PNG')
        metadata={'codec':'rle' if compressed else 'rgb','transfer_bytes':len(body),'decoded_bytes':size,'encoding_ms':encoding_us/1000,'sequence':seq,'target_pid':pid,'width':w,'height':h,'source_width':sw,'source_height':sh,'vblank':vblank,'capture_ms':round((end-start)/1000,3),'capture_started_us':start,'capture_ended_us':end,'may_span_rendered_frames':True,'rgb_sha256':hashlib.sha256(rgb).hexdigest(),'png_sha256':hashlib.sha256(output.getvalue()).hexdigest(),'bridge':timing}
        return output.getvalue(),metadata
    @staticmethod
    def pack_input(target_pid,buttons,ttl_ms,left_stick=None,right_stick=None,front_touch=None,rear_touch=None,abi=1):
        if type(target_pid) is not int or target_pid<=0 or type(ttl_ms) is not int or not 16<=ttl_ms<=1000 or not isinstance(buttons,list) or len(buttons)>12 or any(name not in BUTTONS for name in buttons):
            raise ValueError('Input requires the latest screen PID, known buttons and a 16–1000 ms lease')
        coords=[]; flags=0
        for bit,value,bounds,neutral in [(1,left_stick,(255,255),(128,128)),(2,right_stick,(255,255),(128,128)),(4,front_touch,(1919,1087),(0,0)),(8,rear_touch,(1919,1087),(0,0))]:
            if value is None: coords.extend(neutral); continue
            if not isinstance(value,list) or len(value)!=2 or any(type(v) is not int or not 0<=v<=limit for v,limit in zip(value,bounds)):
                raise ValueError('Invalid stick or raw touch coordinate pair')
            flags|=bit; coords.extend(value)
        mask=0
        for button in buttons: mask|=BUTTONS[button]
        if abi not in (1,2): raise ValueError('Unsupported input ABI')
        return struct.pack('<13Ii',0x31495256,abi,ttl_ms,mask,flags,*coords,target_pid)
    def input(self,target_pid,buttons,ttl_ms,left_stick=None,right_stick=None,front_touch=None,rear_touch=None):
        self.pack_input(target_pid,buttons,ttl_ms,left_stick,right_stick,front_touch,rear_touch)
        self.status()
        return self.json('POST','/input',self.pack_input(target_pid,buttons,ttl_ms,left_stick,right_stick,front_touch,rear_touch,abi=self.abi))
    def release(self): return self.json('POST','/release',b'')
    @staticmethod
    def file_identity(attempt,name):
        if not re.fullmatch('[0-9a-f]{32}',attempt) or not re.fullmatch('[A-Za-z0-9_.-]{1,63}',name) or name in ('.','..'):
            raise ValueError('Invalid managed workspace file identity')
        return attempt+'/'+name
    def read(self,attempt,name,expected_sha256=None):
        path=self.file_identity(attempt,name)
        data,mime,timing=self.request('GET','/workspace/read/'+path,limit=MAX_FILE)
        digest=hashlib.sha256(data).hexdigest()
        if mime!='application/octet-stream' or expected_sha256 is not None and digest!=expected_sha256: raise RuntimeError('Workspace read-back mismatch')
        return data,{'attempt':attempt,'name':name,'bytes':len(data),'sha256':digest,'bridge':timing}
    def publish(self,name,payload):
        attempt=uuid.uuid4().hex; path=self.file_identity(attempt,name); digest=hashlib.sha256(payload).hexdigest()
        if not 0<len(payload)<=MAX_FILE: raise ValueError('Workspace file must be 1 byte to 8 MiB')
        try:
            receipt=self.json('POST','/workspace/write/'+path,payload,digest)
            if receipt.get('attempt')!=attempt or receipt.get('bytes')!=len(payload) or receipt.get('sha256')!=digest or receipt.get('storage_readback') is not True or receipt.get('vita_path')!='ux0:data/vita-control/workspace/'+path:
                raise RuntimeError('Invalid publication receipt')
            checks=[]
            for _ in range(2):
                actual,proof=self.read(attempt,name,digest)
                if actual!=payload: raise RuntimeError('Workspace bytes differ')
                checks.append(proof['bridge'])
            return {'attempt':attempt,'name':name,'bytes':len(payload),'sha256':digest,'vita_path':receipt['vita_path'],'read_back_checks':2,'read_backs':checks,'upload':receipt['bridge'],'installation':'not performed'}
        except Exception as error:
            raise RuntimeError(f'Publication outcome uncertain: attempt {attempt}, name {name}, expected bytes {len(payload)}, SHA-256 {digest}. Read this identity before any new mutation. Cause: {type(error).__name__}') from error


def register(mcp,configuration,root):
    client=ControlClient(configuration)
    @mcp.tool(annotations=READ)
    def vita_control_status()->dict:
        """Read effective driver input, bounded lease state and resident control identity."""
        return client.status()
    @mcp.tool(annotations=READ)
    def vita_control_screen(detail:bool=False)->CallToolResult:
        """Capture the displayed framebuffer, 240x136 preview or up to 480x272 detail. Includes image and timing; may span rendered frames."""
        png,metadata=client.capture(detail)
        return CallToolResult(content=[TextContent(type='text',text=json.dumps(metadata)),Image(data=png,format='png').to_image_content()],structuredContent=metadata)
    @mcp.tool(annotations=WRITE)
    def vita_control_input(target_pid:int,buttons:list[str],ttl_ms:int=250,left_stick:list[int]|None=None,right_stick:list[int]|None=None,front_touch:list[int]|None=None,rear_touch:list[int]|None=None)->dict:
        """Replace synthetic input for the latest screen PID. Lease expires within 1 second; focus changes cancel it. Sticks 0–255 are offsets around 128 added to physical input; raw touch 0–1919,0–1087."""
        return client.input(target_pid,buttons,ttl_ms,left_stick,right_stick,front_touch,rear_touch)
    @mcp.tool(annotations=WRITE)
    def vita_control_release()->dict:
        """Clear all synthetic buttons, sticks and touches immediately."""
        return client.release()
    @mcp.tool(annotations=READ)
    def vita_control_list_files(attempt:str='',offset:int=0)->dict:
        """List up to 32 workspace entries. Empty attempt lists revision directories; use offset for pagination."""
        if attempt and not re.fullmatch('[0-9a-f]{32}',attempt) or type(offset) is not int or not 0<=offset<=1000: raise ValueError('Invalid directory or offset')
        return client.json('GET',f'/workspace/list/{offset}/{attempt}')
    @mcp.tool(annotations=READ)
    def vita_control_file_info(attempt:str,name:str)->dict:
        """Hash and stat one managed workspace file directly on the Vita."""
        return client.json('GET','/workspace/stat/'+client.file_identity(attempt,name))
    @mcp.tool(annotations=READ)
    def vita_control_read_text(attempt:str,name:str,expected_sha256:str)->dict:
        """Read a UTF-8 workspace file of at most 64 KiB and verify its expected hash."""
        if not re.fullmatch('[0-9a-f]{64}',expected_sha256): raise ValueError('Expected SHA-256 is required')
        payload,proof=client.read(attempt,name,expected_sha256)
        if len(payload)>65536: raise ValueError('Text file exceeds 64 KiB; use file_info or copy_file')
        return {**proof,'text':payload.decode('utf-8')}
    @mcp.tool(annotations=WRITE)
    def vita_control_write_text(name:str,text:str)->dict:
        """Publish UTF-8 text as a fresh immutable revision, then verify two byte-for-byte read-backs."""
        payload=text.encode('utf-8')
        if len(payload)>65536: raise ValueError('Text exceeds 64 KiB')
        return client.publish(name,payload)
    @mcp.tool(annotations=WRITE)
    def vita_control_publish_file(relative_file:str,expected_sha256:str)->dict:
        """Publish an exact local file under this project outgoing directory (up to 8 MiB). Never installs or overwrites an app."""
        base=(root/'outgoing').resolve(); source=(base/relative_file).resolve()
        if base not in source.parents or not source.is_file() or not re.fullmatch('[0-9a-f]{64}',expected_sha256): raise ValueError('Choose a file within the outgoing directory and its exact hash')
        with source.open('rb') as handle: payload=handle.read(MAX_FILE+1)
        if hashlib.sha256(payload).hexdigest()!=expected_sha256: raise ValueError('Local artifact hash differs')
        return client.publish(source.name,payload)
    @mcp.tool(annotations=WRITE)
    def vita_control_copy_file(attempt:str,name:str,expected_sha256:str,new_name:str)->dict:
        """Copy a hash-verified workspace file to a fresh revision. Retains the source."""
        if not re.fullmatch('[0-9a-f]{64}',expected_sha256): raise ValueError('Expected SHA-256 is required')
        payload,_=client.read(attempt,name,expected_sha256); return client.publish(new_name,payload)
    @mcp.tool(annotations=REMOVE)
    def vita_control_delete_file(attempt:str,name:str,expected_sha256:str)->dict:
        """Remove one managed workspace file only when its current on-device hash matches. Does not touch system or installed app files."""
        if not re.fullmatch('[0-9a-f]{64}',expected_sha256): raise ValueError('Expected SHA-256 is required')
        return client.json('POST','/workspace/delete/'+client.file_identity(attempt,name),b'',expected_sha256)
    @mcp.tool(annotations=WRITE)
    def vita_control_app(action:Literal['launch','quit'],title_id:Literal['CHRS00003','CHRS00009','CHRS00012'])->dict:
        """Launch or quit DevLoop, Quake or Input Target. Native acceptance is followed by separate screen/runtime observation."""
        if action not in ('launch','quit') or title_id not in ('CHRS00003','CHRS00009','CHRS00012'): raise ValueError('Invalid development app')
        return client.json('POST',f'/app/{action}/{title_id}',b'')
    @mcp.tool(annotations=WRITE)
    def vita_control_sequence(target_pid:int,steps:list[dict])->dict:
        """Run up to 20 prevalidated input steps (total lease time <=5 seconds), capture every result, and release on completion/failure. Writes PC evidence; never replays failed steps."""
        if not isinstance(steps,list) or not 1<=len(steps)<=20: raise ValueError('Choose 1–20 input steps')
        allowed={'buttons','ttl_ms','left_stick','right_stick','front_touch','rear_touch'}
        prepared=[]
        for step in steps:
            if not isinstance(step,dict) or set(step)-allowed: raise ValueError('Unexpected input step fields')
            values={'buttons':[],'ttl_ms':250,**step}
            prepared.append((values,client.pack_input(target_pid,**values)))
        if sum(values['ttl_ms'] for values,payload in prepared)>5000: raise ValueError('Sequence lease time exceeds 5 seconds')
        folder=root/'evidence/control'/('sequence-'+uuid.uuid4().hex);folder.mkdir(parents=True)
        trace={'target_pid':target_pid,'endpoint_host':client.configuration()['host'],'hardware_acceptance':'not inferred from API receipts','steps':[],'result':'pending','started_utc':datetime.now(timezone.utc).isoformat()}
        deadline=time.monotonic()+30
        try:
            png,before=client.capture();(folder/'before.png').write_bytes(png);trace['before']=before
            if before['target_pid']!=target_pid: raise RuntimeError('Foreground changed before sequence')
            for index,(values,payload) in enumerate(prepared):
                if time.monotonic()>=deadline: raise RuntimeError('Sequence time budget expired')
                entry={'index':index,'requested':values,'state':'requesting input'};trace['steps'].append(entry)
                (folder/'trace.json').write_text(json.dumps(trace,indent=2),encoding='utf-8')
                entry['receipt']=client.input(target_pid,**values);entry['state']='input accepted'
                time.sleep(values['ttl_ms']/1000+.02)
                client.release();png,metadata=client.capture();(folder/f'{index+1:02d}.png').write_bytes(png);entry['screen']=metadata
                if metadata['target_pid']!=target_pid: raise RuntimeError('Foreground changed during sequence')
                entry['state']='observed screen; physical response requires image assessment'
            trace['result']='completed input requests and screen observations'
        except Exception as error:
            trace['result']='failed; remaining steps not executed';trace['failure_type']=type(error).__name__
            raise RuntimeError('Sequence stopped; inspect '+str(folder/'trace.json')+' before another sequence') from error
        finally:
            try: trace['final_release']=client.release()
            except Exception: trace['final_release']='unconfirmed; kernel lease expires within 1 second'
            trace['finished_utc']=datetime.now(timezone.utc).isoformat()
            (folder/'trace.json').write_text(json.dumps(trace,indent=2)+'\n',encoding='utf-8')
        return {**trace,'evidence_directory':str(folder)}
    return client
