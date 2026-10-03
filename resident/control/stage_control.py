"""Stage a matched user/kernel pair and config proposal without activating either."""
import argparse
from datetime import datetime,timezone
import ftplib
import io
import json
from pathlib import Path
import re
import sys
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from stage import connect,endpoint,retrieve,save_plan,sha

def proposal(before,user,kernel):
    if not re.fullmatch(r'ux0:data/vita-control/setup-[0-9a-f]{12}-[0-9a-f]{32}/vita_control\.suprx',user) or not re.fullmatch(r'ur0:tai/vita-control/setup-[0-9a-f]{12}-[0-9a-f]{32}/vita_control_kernel\.skprx',kernel): raise ValueError('Unexpected control module paths')
    text=before.decode('utf-8')
    if not before.endswith(b'\n') or '\x00' in text or 'vita_control' in text or 'vita-control/' in text: raise ValueError('Config already refers to control or lacks a terminator')
    if '*main' not in text.splitlines() or '*KERNEL' not in text.splitlines(): raise ValueError('Expected inspected SceShell/kernel configuration')
    ending=b'\r\n' if before.endswith(b'\r\n') else b'\n'
    return before+ending.join([b'# Vita Control prototype (matched pair; normal reboot required)',b'*KERNEL',kernel.encode('ascii'),b'*main',user.encode('ascii'),b''])

def checked_upload(ftp,path,data,allowed):
    if path not in allowed: raise ValueError('Upload escaped this immutable deployment')
    ftp.storbinary('STOR '+path+'.part',io.BytesIO(data),blocksize=16384)
    if retrieve(ftp,path+'.part',len(data))!=data: raise ValueError('Part read-back mismatch')
    ftp.rename(path+'.part',path)
    if retrieve(ftp,path,len(data))!=data: raise ValueError('Final read-back mismatch')

def exists(ftp,path):
    try: ftp.cwd(path); return True
    except ftplib.error_perm as error:
        if str(error).startswith('550'): return False
        raise
    finally: ftp.cwd('/')

def artifacts(root):
    report=json.loads((root/'dist/control/build-report.json').read_text(encoding='utf-8'))
    if report.get('version')!='0.2.2' or not re.fullmatch('[0-9a-f]{64}',report.get('build_id','')): raise ValueError('Unexpected control build identity')
    payloads={}
    for name,leaf in [('vita_control','vita_control.suprx'),('vita_control_kernel','vita_control_kernel.skprx')]:
        info=report['modules'][name];payload=(root/'dist/control'/leaf).read_bytes()
        if info['file']!=leaf or not 0<len(payload)<256*1024 or payload[:4]!=b'SCE\0' or len(payload)!=info['bytes'] or sha(payload)!=info['sha256']: raise ValueError('Control module hash mismatch')
        payloads[leaf]=payload
    for relative,expected in {**report['source_hashes'],**report['accepted_artifacts_preserved']}.items():
        if sha((root/relative).read_bytes())!=expected: raise ValueError('Source or accepted app changed: '+relative)
    return payloads,report

def stage_control(root,expected_config_sha256):
    if not re.fullmatch('[0-9a-f]{64}',expected_config_sha256): raise ValueError('Exact current config SHA-256 is required')
    payloads,report=artifacts(root)
    private=json.loads((root/'.devloop-private/resident.json').read_text(encoding='utf-8'))
    if not re.fullmatch('[0-9a-f]{32}',private.get('token','')): raise ValueError('Invalid existing pairing')
    ftp=connect(endpoint(root/'.devloop-private/ftp.json'));plan_path=None
    try:
        if retrieve(ftp,'/ux0:/tai/config.txt',16384,absent=True) is not None: raise ValueError('Unexpected higher-precedence config')
        before=retrieve(ftp,'/ur0:/tai/config.txt',16384)
        if sha(before)!=expected_config_sha256: raise ValueError('Active config changed')
        pairing=(private['token']+'\n').encode('ascii')
        if retrieve(ftp,'/ux0:/data/vita-resident/bridge.cfg',34)!=pairing: raise ValueError('Pairing differs')
        for path in ['/ux0:/data/vita-control','/ur0:/tai/vita-control']:
            if exists(ftp,path): raise ValueError('Control staging root already exists; inspect its deployment before continuing')
        attempt='setup-'+report['build_id'][:12]+'-'+uuid.uuid4().hex
        native_user='ux0:data/vita-control/'+attempt+'/vita_control.suprx'
        native_kernel='ur0:tai/vita-control/'+attempt+'/vita_control_kernel.skprx'
        after=proposal(before,native_user,native_kernel)
        evidence=root/'evidence/control'/attempt;evidence.mkdir(parents=True,exist_ok=False)
        (evidence/'config.txt.before-control').write_bytes(before);(evidence/'config.txt.proposed').write_bytes(after)
        userdir='/ux0:/data/vita-control/'+attempt;kerneldir='/ur0:/tai/vita-control/'+attempt
        files={userdir+'/vita_control.suprx':payloads['vita_control.suprx'],kerneldir+'/vita_control_kernel.skprx':payloads['vita_control_kernel.skprx'],userdir+'/config.txt':after,userdir+'/rollback/config.txt':before,userdir+'/LICENSE.vitacompanion':(root/'resident/control/LICENSE.vitacompanion').read_bytes()}
        plan={'prepared_utc':datetime.now(timezone.utc).isoformat(),'build_id':report['build_id'],'version':report['version'],'attempt':attempt,'user_plugin':native_user,'kernel_plugin':native_kernel,'vita_directory':'ux0:data/vita-control/'+attempt,'active_config_before_sha256':sha(before),'proposed_config_sha256':sha(after),'pairing_preserved':True,'active_config_unchanged':False,'state':'prepared; writes pending','files':{path:{'bytes':len(data),'sha256':sha(data),'read_back_checks':0} for path,data in files.items()},'local_evidence':str(evidence)}
        plan_path=evidence/'deployment.json';save_plan(plan_path,plan)
        for path in ['/ux0:/data/vita-control','/ux0:/data/vita-control/workspace',userdir,userdir+'/rollback','/ur0:/tai/vita-control',kerneldir]: ftp.mkd(path)
        plan['state']='staging; failures require read-only inspection';save_plan(plan_path,plan)
        for path,data in files.items():
            checked_upload(ftp,path,data,set(files));plan['files'][path]['read_back_checks']=2;save_plan(plan_path,plan)
        if retrieve(ftp,'/ur0:/tai/config.txt',16384)!=before or retrieve(ftp,'/ux0:/data/vita-resident/bridge.cfg',34)!=pairing: raise ValueError('Configuration or pairing changed during staging')
        plan['active_config_unchanged']=True;plan['state']='verified staged pair; manual config copy and normal shutdown/start pending';save_plan(plan_path,plan);return plan
    except Exception as error:
        if plan_path is not None:
            plan['state']='staging failed or outcome uncertain; do not replay';plan['failure_type']=type(error).__name__;save_plan(plan_path,plan)
        raise RuntimeError('Control staging failed; this procedure never writes active config') from error
    finally: ftp.close()

if __name__=='__main__':
    raise SystemExit('Legacy boot proposal disabled. Use stage_starter.py for runtime activation.')
    parser=argparse.ArgumentParser();parser.add_argument('--expected-config-sha256',required=True)
    print(json.dumps(stage_control(ROOT,parser.parse_args().expected_config_sha256),indent=2))
