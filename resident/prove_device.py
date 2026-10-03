"""Collect bounded live proof through MCP; foreground app labels come from the user."""
import argparse
import asyncio
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def describe_error(error):
    if isinstance(error, BaseExceptionGroup):
        return ' | '.join(describe_error(item) for item in error.exceptions)
    return str(error)


async def call(session, tool, arguments):
    result = await session.call_tool(tool, arguments)
    if result.isError:
        raise RuntimeError(result.content[0].text)
    return result.structuredContent or json.loads(result.content[0].text)


async def prove(args):
    config = json.loads((ROOT / '.devloop-private/resident.json').read_text(encoding='utf-8'))
    address = ipaddress.IPv4Address(config['host'])
    if address.is_loopback or not address.is_private or config['port'] != 17866:
        raise ValueError('Live proof requires the paired LAN device on port 17866')
    build = json.loads((ROOT / 'dist/resident/build-report.json').read_text(encoding='utf-8'))
    folder = ROOT / 'evidence/resident' / ('live-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(exist_ok=False)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'user_reported_foreground': args.label, 'device_endpoint': f'{address}:17866', 'plugin_sha256': build['plugin']['sha256'], 'expected_build_id': build['plugin']['build_id'], 'samples': [], 'result': 'pending', 'physical_acceptance': 'user confirmation of image, controls, audio and stability is separate'}
    output = folder / 'proof.json'
    try:
        parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'resident/bridge.py')])
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for _ in range(3):
                    sample = await call(session, 'vita_resident_status', {})
                    report['samples'].append(sample)
                    if sample['build_id'] != report['expected_build_id'] or sample.get('port') != 17866 or sample.get('process') != 'SceShell user plugin' or sample.get('keep_awake') is not False:
                        raise ValueError('The running resident build/capabilities differ from this proof target')
                    await asyncio.sleep(1)
                first, last = report['samples'][0], report['samples'][-1]
                if any(item['started_ms'] != first['started_ms'] for item in report['samples']) or last['uptime_ms'] <= first['uptime_ms'] or last['heartbeat'] <= first['heartbeat']:
                    raise ValueError('Resident instance changed or heartbeat did not advance')
                if args.previous:
                    previous = json.loads(args.previous.read_text(encoding='utf-8'))
                    if previous['result'] != 'passed device MCP checks' or previous['expected_build_id'] != report['expected_build_id'] or previous['samples'][-1]['started_ms'] != first['started_ms']:
                        raise ValueError('The service restarted since the previous proof')
                    report['same_instance_as'] = str(args.previous.resolve())
                if args.probe:
                    report['probe_upload'] = await call(session, 'vita_resident_probe_upload', {})
                if args.package:
                    if not args.expected_sha256:
                        raise ValueError('Package staging requires its exact SHA-256')
                    report['package_upload'] = await call(session, 'vita_resident_stage_package', {'package': args.package, 'expected_sha256': args.expected_sha256})
                report['after'] = await call(session, 'vita_resident_status', {})
                if report['after']['started_ms'] != first['started_ms'] or report['after']['build_id'] != report['expected_build_id']:
                    raise ValueError('Resident instance changed during this proof')
                report['result'] = 'passed device MCP checks'
    except Exception as error:
        report['result'] = 'failed or interrupted device MCP checks'
        report['error'] = describe_error(error)
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'result': report['result'], 'evidence': str(output)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--label', choices=['livearea', 'devloop', 'other-app', 'after-app-return', 'after-wake'], required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--package', choices=['devloop'])
    parser.add_argument('--expected-sha256')
    try:
        asyncio.run(prove(parser.parse_args()))
    except Exception as error:
        print(describe_error(error), file=sys.stderr)
        raise SystemExit(1)
