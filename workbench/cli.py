"""python -m workbench.cli doctor | prepare BUILD | trial PROFILE HASH BUILD | soak SECONDS BUILD | report PATH"""
import argparse
import json
from .runner import run_trial
from .server import doctor,soak,read_report
from .prepare import prepare
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--build')
    q=sub.add_parser('prepare');q.add_argument('build');q.add_argument('--version',choices=['01.02','01.03','01.04'],default='01.04');q.add_argument('--timeout',type=int,default=30);q.add_argument('--devloop-build');q.add_argument('--script-only',action='store_true',help='Permit script-ready success without verified foreground input mapping')
    t=sub.add_parser('trial');t.add_argument('profile');t.add_argument('sha256');t.add_argument('build');t.add_argument('--devloop-build')
    s=sub.add_parser('soak');s.add_argument('seconds',type=int);s.add_argument('build')
    r=sub.add_parser('report');r.add_argument('path')
    a=p.parse_args();value=doctor(a.build) if a.command=='doctor' else prepare(a.build,a.version,a.timeout,expected_devloop_build=a.devloop_build) if a.command=='prepare' else run_trial(a.profile,a.sha256,a.build,expected_devloop_build=a.devloop_build) if a.command=='trial' else soak(a.seconds,a.build) if a.command=='soak' else read_report(a.path)
    print(json.dumps(value,indent=2))
    if a.command=='prepare':return 0 if value.get('ready_for_input_trial') or a.script_only and value.get('ready_for_script_reload') else 1
    return 1 if str(value.get('result','')).startswith('failed') or value.get('result')=='blocked' else 0
if __name__=='__main__':raise SystemExit(main())
