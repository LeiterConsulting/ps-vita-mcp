"""Run portable host contracts only; never connects to or qualifies a Vita."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'evidence/ci'
    output.mkdir(parents=True, exist_ok=True)
    image = json.loads((ROOT / 'toolchain.lock.json').read_text())['image']
    # Linux bind mounts retain numeric ownership; root containers would leave
    # evidence directories unwritable to the following host-side MCP fixtures.
    user = ['--user', f'{os.getuid()}:{os.getgid()}'] if os.name == 'posix' else []
    checks = [(name, ['docker', 'run', '--rm', '--network', 'none', *user, '--mount',
                      f'type=bind,source={ROOT},target=/workspace', image, 'sh', script])
              for name, script in [('devloop-c', 'scripts/test_devloop.sh'),
                                   ('resident-c', 'resident/test_host.sh'),
                                   ('control-c', 'resident/control/test_host.sh'),
                                   ('target-c', 'workbench/target/test_host.sh')]]
    checks += [(Path(script).stem + '-' + Path(script).parent.name, [sys.executable, script])
               for script in ['tests/test_bridge.py', 'tests/test_scripts_bridge.py',
                              'resident/test_bridge.py', 'resident/control/test_bridge.py',
                              'resident/control/test_staging.py', 'workbench/test_mcp.py']]
    checks.append(('workbench-decisions', [sys.executable, '-m', 'unittest',
                   'workbench.test_qualification', 'workbench.test_power',
                   'workbench.test_physical', 'workbench.test_disconnect', 'workbench.test_journal']))
    report = {'scope': 'Host code and actual stdio MCP against simulated local adapters; no device acceptance', 'checks': []}
    for name, command in checks:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
        (output / (name + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        report['checks'].append({'name': name, 'exit_code': result.returncode})
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(('PASS ' if result.returncode == 0 else 'FAIL ') + name, flush=True)
        if result.returncode:
            print((result.stdout + result.stderr)[-6000:])
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
