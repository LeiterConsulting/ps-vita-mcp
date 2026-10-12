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
    checks = [('public-source-scope', [sys.executable, 'scripts/check_public_scope.py']),
              ('pc-pairing-form', [sys.executable, 'tools/pairing_check.py', '--self-test']),
              ('devloop-native-identity', [sys.executable, 'tests/test_devloop_identity.py'])]
    checks += [(name, ['docker', 'run', '--rm', '--network', 'none', *user, '--mount',
                      f'type=bind,source={ROOT},target=/workspace', image, 'sh', script])
              for name, script in [('devloop-c', 'scripts/test_devloop.sh'),
                                   ('resident-c', 'resident/test_host.sh'),
                                   ('control-c', 'resident/control/test_host.sh'),
                                   ('autostart-c', 'resident/autostart/test_host.sh'),
                                   ('boot-diagnostic-c', 'resident/boot_diagnostic/test_host.sh'),
                                   ('launch-broker-c', 'resident/launch_broker/test_host.sh'),
                                   ('native-launch-c', 'resident/native_launch/test_host.sh'),
                                   ('native-install-c', 'resident/native_install/test_host.sh'),
                                   ('native-lab-c', 'lifecycle_lab/test_host.sh'),
                                   ('target-c', 'workbench/target/test_host.sh'),
                                   ('vita-app-native-c', 'scripts/test_vita_app_native.sh')]]
    checks += [(Path(script).stem + '-' + Path(script).parent.name, [sys.executable, script])
               for script in ['tests/test_bridge.py', 'tests/test_scripts_bridge.py',
                              'resident/test_bridge.py', 'resident/test_files_bridge.py', 'resident/control/test_bridge.py',
                              'resident/control/test_staging.py', 'workbench/test_mcp.py']]
    checks.append(('launch-broker-http', [sys.executable, 'tests/test_launch_broker_http.py']))
    checks.append(('native-lifecycle-pc', [sys.executable, '-m', 'unittest', 'workbench.test_native_lifecycle']))
    checks.append(('vita-app-projects', [sys.executable, '-m', 'unittest',
                                       'tools.test_vita_app', 'app_slot.test_native_slot',
                                       'app_slot.test_dependency_integration']))
    checks.append(('vita-app-shared-lua', [sys.executable, '-m', 'unittest', 'app_tools.test_lua_check']))
    checks.append(('script-session-http', [sys.executable, '-m', 'unittest', 'workbench.test_script_session']))
    checks.append(('script-session-mcp-cli', [sys.executable, '-m', 'unittest', 'workbench.test_script_session_mcp']))
    checks.append(('script-demo-real-lua', [sys.executable, 'tests/test_script_demo.py']))
    checks.append(('workbench-decisions', [sys.executable, '-m', 'unittest',
                   'workbench.test_prepare', 'workbench.test_endpoints', 'workbench.test_qualification', 'workbench.test_power',
                   'workbench.test_physical', 'workbench.test_disconnect', 'workbench.test_journal']))
    checks.append(('autostart-staging', [sys.executable, '-m', 'unittest',
                   'resident.autostart.test_staging']))
    report = {'scope': 'Host code and actual stdio MCP against simulated local adapters; no device acceptance', 'checks': []}
    for name, command in checks:
        environment = dict(os.environ)
        if name == 'vita-app-shared-lua': environment['VITA_APP_TEST_DOCKER'] = '1'
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                                timeout=600, env=environment)
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
