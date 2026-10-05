"""python -m workbench.cli doctor | trial PROFILE HASH BUILD | soak SECONDS BUILD | report PATH"""
import argparse
import json
from .runner import run_trial
from .server import doctor,soak,read_report
def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--build')
    t=sub.add_parser('trial');t.add_argument('profile');t.add_argument('sha256');t.add_argument('build')
    s=sub.add_parser('soak');s.add_argument('seconds',type=int);s.add_argument('build')
    r=sub.add_parser('report');r.add_argument('path')
    a=p.parse_args();value=doctor(a.build) if a.command=='doctor' else run_trial(a.profile,a.sha256,a.build) if a.command=='trial' else soak(a.seconds,a.build) if a.command=='soak' else read_report(a.path)
    print(json.dumps(value,indent=2));return 1 if str(value.get('result','')).startswith('failed') else 0
if __name__=='__main__':raise SystemExit(main())
