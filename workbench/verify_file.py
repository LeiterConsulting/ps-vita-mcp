"""Recover an uncertain managed-file outcome by observation, without rewriting it."""
import hashlib,http.client,json,os,re,time
from .runner import Device,Journal,WORKDIR,check_identity,utc
from .session import exclusive
from .power import WorkKeeper

MAX_FILE=8*1024*1024
def read_wire(client,path,limit):
    config=client.configuration();port=int(os.environ.get('VITA_CONTROL_PORT',config['port']+1))
    if not 1<=port<=65535:raise ValueError('Invalid Control port')
    connection=http.client.HTTPConnection(config['host'],port,timeout=30)
    start=time.monotonic()
    try:
        connection.request('GET',path,headers={'Authorization':'Bearer '+config['token'],'Connection':'close'})
        response=connection.getresponse();payload=response.read(limit+1)
        if response.status!=200 or len(payload)>limit:raise RuntimeError('Read-only file observation rejected or exceeded its bound')
        return payload,response.getheader('Content-Type','').split(';')[0],round((time.monotonic()-start)*1000,2)
    finally:connection.close()

def verify(attempt,name,expected_bytes,expected_sha256,expected_control_build,device=None,root=WORKDIR):
    if not re.fullmatch('[0-9a-f]{32}',attempt) or not re.fullmatch('[A-Za-z0-9_.-]{1,63}',name) or name in ('.','..'):raise ValueError('Pin one managed file identity')
    if type(expected_bytes) is not int or not 1<=expected_bytes<=MAX_FILE or not re.fullmatch('[0-9a-f]{64}',expected_sha256):raise ValueError('Pin exact file size and SHA-256')
    if not re.fullmatch('[0-9a-f]{64}',expected_control_build):raise ValueError('Pin the exact Control build')
    d=device or Device();identity=attempt+'/'+name
    with exclusive():
        j=Journal(root,'file-verification');keeper=WorkKeeper(d.control,j.folder)
        j.report.update(attempt=attempt,name=name,expected_bytes=expected_bytes,expected_sha256=expected_sha256,control_build=expected_control_build,device_file_mutations=0)
        try:
            check_identity(d.control_status(),expected_control_build)
            def stat():
                raw,mime,ms=read_wire(d.control,'/workspace/stat/'+identity,8192)
                if mime!='application/json':raise RuntimeError('Unexpected native hash format')
                info=json.loads(raw)
                if info.get('bytes')!=expected_bytes or info.get('sha256')!=expected_sha256 or info.get('vita_path')!='ux0:data/vita-control/workspace/'+identity:raise RuntimeError('Native file identity, size or hash differs')
                return {**info,'round_trip_ms':ms}
            j.report['native_before']=stat();keeper.start(d.control_status());j.report['readbacks']=[];first=None
            for number in range(2):
                j.event('read_intent',{'number':number+1,'identity':identity})
                payload,mime,ms=read_wire(d.control,'/workspace/read/'+identity,expected_bytes)
                if mime!='application/octet-stream' or len(payload)!=expected_bytes or hashlib.sha256(payload).hexdigest()!=expected_sha256 or first is not None and payload!=first:raise RuntimeError('Full file readback differs; no read or mutation replayed')
                first=payload;j.report['readbacks'].append({'number':number+1,'bytes':len(payload),'sha256':expected_sha256,'round_trip_ms':ms});j.save()
            j.report['native_after']=stat();check_identity(d.control_status(),expected_control_build)
            artifact=j.folder/'verified.bin';artifact.write_bytes(first);j.report.update(result='passed',read_back_checks=2,local_artifact=str(artifact))
        except Exception as error:j.report.update(result='failed',failure_type=type(error).__name__,failure=str(error)[:240])
        finally:
            j.report['work_power']=keeper.stop();j.report['finished_utc']=utc();j.save()
        return {**j.report,'evidence_directory':str(j.folder)}
