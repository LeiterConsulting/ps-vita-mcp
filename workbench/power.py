"""Temporary work power leases. Renewal never represents physical device activity."""
import http.client
import json
import os
import struct
import threading
import time
from datetime import datetime,timezone

def pack(ttl_ms=30000,idle_ms=30000,dim_percent=20):
    if any(type(v) is not int for v in (ttl_ms,idle_ms,dim_percent)) or ttl_ms not in (0,) and not 5000<=ttl_ms<=30000 or not 5000<=idle_ms<=120000 or not 5<=dim_percent<=50:
        raise ValueError('Work lease needs 0 or 5000..30000 ms, idle 5000..120000 ms, and brightness 5..50 percent')
    return struct.pack('<5I',0x31505756,2,ttl_ms,idle_ms,dim_percent)

def validate(value):
    if value.get('app')!='Vita Work Power' or value.get('abi')!=2 or type(value.get('lease_remaining_ms')) is not int or not 0<=value['lease_remaining_ms']<=30000 or type(value.get('dimmed')) is not bool:
        raise RuntimeError('Invalid work power reply')
    return value

def status(client):return validate(client.json('GET','/power/status'))
def lease(client,ttl_ms=30000,idle_ms=30000,dim_percent=20):
    body=pack(ttl_ms,idle_ms,dim_percent) # Validate before contacting the device.
    identity=client.status()
    if identity.get('abi')!=2 or identity.get('power_protocol')!=1:raise RuntimeError('Install the current Control Starter for work power support')
    value=validate(client.json('POST','/power/lease',body));client.work_renewed=time.monotonic() if ttl_ms else 0
    return value

class WorkKeeper:
    """Renew only /power/lease while an exclusive job owns the Workbench lock.

    The heartbeat thread has a dedicated bounded HTTP connection because the
    main thread holds that lock throughout the job. It cannot send inputs or files.
    An uncertain heartbeat is recorded once and stops renewal until a new job.
    """
    def __init__(self,client,folder,interval=10):
        self.client=client;self.folder=folder;self.interval=interval;self.end=threading.Event();self.thread=None
        self.result={'enabled':False,'ttl_ms':30000,'idle_ms':30000,'dim_percent':20,'renewals':0,'errors':[]}
    def record(self,kind,**fields):
        with (self.folder/'power.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'kind':kind,**fields})+'\n');f.flush();os.fsync(f.fileno())
    def send(self,ttl):
        body=pack(ttl);config=self.client.configuration();port=int(os.environ.get('VITA_CONTROL_PORT',config['port']+1))
        if not 1<=port<=65535:raise ValueError('Invalid Control port')
        self.record('lease_intent',ttl_ms=ttl)
        c=http.client.HTTPConnection(config['host'],port,timeout=5)
        try:
            c.request('POST','/power/lease',body,{'Authorization':'Bearer '+config['token'],'Connection':'close'})
            r=c.getresponse();raw=r.read(8193)
            if r.status!=200 or len(raw)>8192 or r.getheader('Content-Type','').split(';')[0]!='application/json':raise RuntimeError('Work lease reply rejected')
            value=validate(json.loads(raw));self.client.work_renewed=time.monotonic() if ttl else 0;self.record('lease_receipt',ttl_ms=ttl,remaining_ms=value['lease_remaining_ms'])
            return value
        except Exception as error:
            self.record('lease_unconfirmed',ttl_ms=ttl,failure_type=type(error).__name__,replayed=False)
            raise
        finally:c.close()
    def start(self,identity):
        if identity.get('abi')!=2 or identity.get('power_protocol')!=1:
            self.result['reason']='Endpoint does not advertise temporary work power support';return
        self.send(30000);self.result['enabled']=True
        def run():
            while not self.end.wait(self.interval):
                try:self.send(30000);self.result['renewals']+=1
                except Exception as error:
                    self.result['errors'].append(type(error).__name__);self.end.set();break
        self.thread=threading.Thread(target=run,name='vita-work-lease',daemon=True);self.thread.start()
    def stop(self):
        self.end.set()
        if self.thread:self.thread.join(timeout=6)
        if self.result['enabled']:
            if self.thread and self.thread.is_alive():self.result['end']='unconfirmed; lease expires within 30 seconds of its last accepted renewal'
            else:
                try:self.send(0);self.result['end']='ended; native worker restores brightness'
                except Exception:self.result['end']='unconfirmed; lease expires within 30 seconds of its last accepted renewal'
        return self.result
