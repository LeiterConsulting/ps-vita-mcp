"""Workbench inspection, preparation, hash-pinned script sessions and input trials."""
import argparse
import json
import hashlib
from pathlib import Path
from .script_session import run_session
from resident.launch_client import prepare_script_session
from .runner import run_trial
from .server import doctor,soak,read_report
from .prepare import prepare
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--build')
    q=sub.add_parser('prepare');q.add_argument('build');q.add_argument('--version',choices=['01.02','01.03','01.04'],default='01.04');q.add_argument('--timeout',type=int,default=30);q.add_argument('--devloop-build');q.add_argument('--script-only',action='store_true',help='Permit script-ready success without verified foreground input mapping')
    c=sub.add_parser('prepare-script');c.add_argument('build');c.add_argument('--allow-launch',action='store_true');c.add_argument('--resident-build');c.add_argument('--resident-instance');c.add_argument('--timeout',type=int,default=15)
    c=sub.add_parser('script-session');c.add_argument('manifest');c.add_argument('sha256',help='Exact SHA-256 of the UTF-8 JSON manifest')
    t=sub.add_parser('trial');t.add_argument('profile');t.add_argument('sha256');t.add_argument('build');t.add_argument('--devloop-build')
    s=sub.add_parser('soak');s.add_argument('seconds',type=int);s.add_argument('build')
    r=sub.add_parser('report');r.add_argument('path')
    a=p.parse_args()
    if a.command=='script-session':
        with Path(a.manifest).open('rb') as manifest_file:raw=manifest_file.read(150*1024+1)
        if not 0<len(raw)<=150*1024 or hashlib.sha256(raw).hexdigest()!=a.sha256:raise ValueError('Manifest hash differs or exceeds 150 KiB')
        manifest=json.loads(raw)
        allowed={'candidates','expected_devloop_build','expected_pid','expected_run','expected_revision','retain_best','selection'}
        if not isinstance(manifest,dict) or set(manifest)-allowed:raise ValueError('Unknown script-session manifest fields')
        value=run_session(**manifest)
    elif a.command=='prepare-script':value=prepare_script_session(a.build,allow_launch=a.allow_launch,expected_resident_build=a.resident_build,expected_resident_instance=a.resident_instance,timeout_s=a.timeout)
    else:value=doctor(a.build) if a.command=='doctor' else prepare(a.build,a.version,a.timeout,expected_devloop_build=a.devloop_build) if a.command=='prepare' else run_trial(a.profile,a.sha256,a.build,expected_devloop_build=a.devloop_build) if a.command=='trial' else soak(a.seconds,a.build) if a.command=='soak' else read_report(a.path)
    print(json.dumps(value,indent=2))
    if a.command=='prepare':return 0 if value.get('ready_for_input_trial') or a.script_only and value.get('ready_for_script_reload') else 1
    if a.command=='prepare-script':return 0 if value.get('ready_for_script_reload') else 1
    if a.command=='script-session':return 0 if value.get('result')=='passed' else 1
    return 1 if str(value.get('result','')).startswith('failed') or value.get('result')=='blocked' else 0
if __name__=='__main__':raise SystemExit(main())
