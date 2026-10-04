"""Publish a runtime Starter VPK to a fresh inbox; never install or activate it."""
import argparse,ftplib,hashlib,io,json,re,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from stage import connect,endpoint,retrieve,sha
sys.path.insert(0,str(ROOT/'bridge'))
from ftp_staging import enter_shared_directory,verify_remote

def stage_starter(root,expected_package,expected_config):
    if not all(re.fullmatch('[0-9a-f]{64}',value) for value in [expected_package,expected_config]):raise ValueError('Exact package/config hashes required')
    report=json.loads((root/'dist/control/build-report.json').read_text())
    package=report['starter_package'];payload=(root/'dist/control/control_starter.vpk').read_bytes()
    if report['version']!='0.3.3' or package['titleId']!='CHRS00011' or package['version']!='01.04' or package['sha256']!=expected_package or sha(payload)!=expected_package or len(payload)!=package['bytes'] or not 0<len(payload)<=2*1024*1024:
        raise ValueError('Starter package differs from exact build evidence')
    for relative,digest in {**report['source_hashes'],**report['accepted_artifacts_preserved']}.items():
        if sha((root/relative).read_bytes())!=digest:raise ValueError('Recorded source/accepted artifact changed; rebuild before staging')
    private=json.loads((root/'.devloop-private/resident.json').read_text());settings=endpoint(root/'.devloop-private/ftp.json')
    if private.get('host')!=settings['host'] or not re.fullmatch('[0-9a-f]{32}',private.get('token','')):raise ValueError('Pairing/FTP device identity differs')
    attempt='01.04-'+expected_package[:12]+'-'+uuid.uuid4().hex
    folder=root/'evidence/control'/('starter-stage-'+attempt);folder.mkdir(parents=True,exist_ok=False)
    remote='ux0:data/vita-control/inbox/'+attempt
    receipt={'prepared_utc':datetime.now(timezone.utc).isoformat(),'state':'preflight','version':'01.04','service_version':report['version'],'build_id':report['build_id'],'sha256':expected_package,'bytes':len(payload),'vita_path':remote+'/control_starter.vpk','read_back_checks':0,'installation':'manual pending','activation':'not performed; normal reboot and manual foreground CROSS required','active_config_unchanged':False,'pairing_unchanged':False,'session_guard':'must be absent before first runtime start','evidence':str(folder)}
    def save():(folder/'deployment.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    ftp=connect(settings)
    try:
        config=retrieve(ftp,'/ur0:/tai/config.txt',16384)
        if sha(config)!=expected_config or retrieve(ftp,'/ux0:/tai/config.txt',16384,absent=True) is not None:raise ValueError('Recovered boot configuration differs')
        pairing=(private['token']+'\n').encode('ascii')
        if retrieve(ftp,'/ux0:/data/vita-resident/bridge.cfg',34)!=pairing:raise ValueError('Existing resident pairing differs')
        guard=retrieve(ftp,'/ux0:/data/vita-control/control-session.lock',256,absent=True)
        if guard is not None:raise ValueError('Runtime session guard already exists; confirm reboot and inspect before retiring it')
        (folder/'config.active.txt').write_bytes(config)
        try:ftp.cwd('/ux0:/app/CHRS00011')
        except ftplib.error_perm as error:
            if not str(error).startswith('550'):raise
        else:
            files={item['name']:item for item in package['files']};installed={}
            for name in ['eboot.bin','vita_control_kernel.skprx','vita_control.suprx','control_bootstrap_probe.suprx','sce_sys/param.sfo']:
                data=retrieve(ftp,'/ux0:/app/CHRS00011/'+name,1024*1024)
                if len(data)!=files[name]['bytes'] or sha(data)!=files[name]['sha256']:raise ValueError('Unknown installed Starter identity')
                target=folder/'previous-installed'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                installed[name]={'bytes':len(data),'sha256':sha(data)}
            receipt['previous_installed']=installed
        ftp.cwd('/ux0:/data');enter_shared_directory(ftp,'vita-control');enter_shared_directory(ftp,'inbox');ftp.mkd(attempt);ftp.cwd(attempt)
        if ftp.pwd()!='/'+remote.replace('ux0:','ux0:/',1):raise ValueError('Unexpected Starter inbox path')
        receipt['state']='writing fresh package part';save()
        ftp.storbinary('STOR control_starter.vpk.part',io.BytesIO(payload),blocksize=16384)
        verify_remote(ftp,'control_starter.vpk.part',package);receipt['read_back_checks']=1;receipt['state']='part verified; publishing';save()
        ftp.rename('control_starter.vpk.part','control_starter.vpk');verify_remote(ftp,'control_starter.vpk',package);receipt['read_back_checks']=2
        if retrieve(ftp,'/ur0:/tai/config.txt',16384)!=config or retrieve(ftp,'/ux0:/data/vita-resident/bridge.cfg',34)!=pairing or retrieve(ftp,'/ux0:/data/vita-control/control-session.lock',256,absent=True) is not None:
            raise ValueError('Boot config, pairing or runtime guard changed during publication')
        receipt['active_config_unchanged']=receipt['pairing_unchanged']=True
        receipt['state']='verified staged Starter; manual installation/reboot/runtime start pending';receipt['verified_utc']=datetime.now(timezone.utc).isoformat();save();return receipt
    except Exception as error:
        receipt['state']='failed or outcome uncertain; no replay, installation or activation';receipt['failure_type']=type(error).__name__;save()
        raise RuntimeError('Starter staging failed; active config, pairing and modules were never changed') from None
    finally:ftp.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sha256',required=True);parser.add_argument('--expected-config-sha256',required=True);args=parser.parse_args()
    print(json.dumps(stage_starter(ROOT,args.sha256,args.expected_config_sha256),indent=2))
