"""Create/check Vita projects and generate fresh MCP arguments; no device calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ROUTES = ('lua', 'native-slot')
SLUG = re.compile(r'[a-z][a-z0-9-]{0,31}')
DEFAULT_CHECKS = [{'metric': 'frames', 'min': 30}, {'metric': 'seconds', 'min': 0.25},
                  {'metric': 'bounds_ok', 'equals': 1}, {'metric': 'collisions', 'min': 1},
                  {'metric': 'score', 'min': 1}, {'metric': 'paddle_x', 'min': 90, 'max': 870},
                  {'metric': 'ball_x', 'min': 48, 'max': 912}]


def read_json(path, limit=16384):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate JSON field')
            value[key] = item
        return value
    raw = Path(path).read_bytes()
    if not 0 < len(raw) <= limit:
        raise ValueError('JSON is empty or exceeds its bound')
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def project_path(slug, *, root=ROOT):
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError('Choose a 1..32 character lowercase project identifier starting with a letter')
    root = Path(root).resolve()
    base = root / '.devloop-private/vita-apps'
    for parent in (base.parent, base):
        if parent.is_symlink() or parent.exists() and parent.resolve() != parent.absolute():
            raise ValueError('Private project parents must not be links or junctions')
    path = base / slug
    # Project identifiers are not paths; reparse points must not redirect output.
    if root not in base.parents or path.resolve() != path:
        raise ValueError('Project directory must not redirect outside the private project area')
    return path


def validate_checks(checks):
    if not isinstance(checks, list) or not 1 <= len(checks) <= 8:
        raise ValueError('Provide 1..8 app metric checks')
    for item in checks:
        if (not isinstance(item, dict) or set(item) - {'metric', 'equals', 'min', 'max'}
                or not isinstance(item.get('metric'), str)
                or not re.fullmatch(r'[A-Za-z0-9_]{1,24}', item['metric'])
                or not set(item) & {'equals', 'min', 'max'}
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for k, v in item.items() if k != 'metric')
                or 'min' in item and 'max' in item and item['min'] > item['max']):
            raise ValueError('Invalid finite app metric predicate')
    return checks


def load(slug, *, root=ROOT):
    path = project_path(slug, root=root)
    value = read_json(path / 'vita-project.json')
    if (set(value) != {'schema_version', 'slug', 'name', 'intent', 'route', 'checks', 'host_frames'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['slug'] != slug or value['route'] not in ROUTES
            or not isinstance(value['name'], str) or not 1 <= len(value['name']) <= 64
            or any(ord(ch) < 32 or ord(ch) > 126 for ch in value['name'])
            or not isinstance(value['intent'], str) or len(value['intent']) > 2000
            or type(value['host_frames']) is not int or not 1 <= value['host_frames'] <= 3600):
        raise ValueError('Invalid Vita project manifest')
    if value['route'] == 'lua':
        validate_checks(value['checks'])
    elif value['checks'] != []:
        raise ValueError('Native behavior checks belong in the module self-test and host assertions')
    return path, value


def create(slug, route, name=None, intent='', *, root=ROOT):
    path = project_path(slug, root=root)
    if route not in ROUTES:
        raise ValueError('Choose lua or native-slot')
    name = name or slug.replace('-', ' ').title()
    if (not isinstance(name, str) or not 1 <= len(name) <= 64
            or any(ord(ch) < 32 or ord(ch) > 126 for ch in name)
            or not isinstance(intent, str) or len(intent) > 2000):
        raise ValueError('Use a printable ASCII display name and bounded intent')
    if route == 'native-slot' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,47}', name):
        raise ValueError('Native slot names need 1..48 ASCII letters, digits, spaces, underscores or hyphens')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive mkdir prevents replacing an existing project or its sources.
    path.mkdir()
    manifest = {'schema_version': 1, 'slug': slug, 'name': name, 'intent': intent,
                'route': route, 'checks': DEFAULT_CHECKS if route == 'lua' else [], 'host_frames': 120}
    if route == 'lua':
        shutil.copyfile(Path(root) / 'app_tools/lua_starter.lua', path / 'main.lua')
    else:
        from scripts.vita_native_slot import scaffold
        scaffold(path / 'native-slot', name=slug, display_name=name, root=Path(root))
    write_json(path / 'vita-project.json', manifest)
    (path / 'PLAN.md').write_text(
        f'# {name}\n\n{intent or "Implement the requested app behavior and record its acceptance here."}\n\n'
        f'Delivery route: `{route}`.\n\n'
        'Automated checks belong in the project manifest/module tests. '
        'Record visual and physical testing separately.\n', encoding='utf-8')
    return {'result': 'created', 'route': route, 'project': str(path),
            'manifest': str(path / 'vita-project.json'), 'device_mutations': 0}


def check_project(slug, *, root=ROOT):
    path, manifest = load(slug, root=root)
    if manifest['route'] == 'lua':
        from app_tools.lua_check import check
        return check(path / 'main.lua', manifest['checks'], frames=manifest['host_frames'], repo=Path(root))
    from scripts.vita_native_slot import check
    return check(path / 'native-slot', root=Path(root))


def build_project(slug, version='01.02', *, root=ROOT):
    path, manifest = load(slug, root=root)
    if manifest['route'] != 'native-slot':
        raise ValueError('Lua scenes use check and session-args; they are not standalone VPKs')
    from scripts.vita_native_slot import build
    return build(path / 'native-slot', version=version, root=Path(root))


def session_args(slug, preparation, duration_s=1.5, retain_best=False, *, root=ROOT):
    path, manifest = load(slug, root=root)
    if manifest['route'] != 'lua':
        raise ValueError('Use native preview/execute for a native-slot project')
    if not isinstance(preparation, dict):
        raise ValueError('Supply fresh successful DevLoop preparation JSON')
    identity = preparation.get('runtime_identity')
    if (preparation.get('ready_for_script_reload') is not True or not isinstance(identity, dict)
            or identity.get('app') != 'Vita DevLoop' or identity.get('protocol') != 1
            or identity.get('version') != '01.04' or identity.get('title_id') != 'CHRS00003'):
        raise ValueError('Supply fresh successful DevLoop 01.04 preparation JSON')
    with (path / 'main.lua').open('rb') as source_file:
        source = source_file.read(16385)
    candidate = {'name': slug, 'source': source.decode('utf-8'),
                 'source_sha256': hashlib.sha256(source).hexdigest(),
                 'duration_s': duration_s, 'warmup_s': 0.25, 'checks': manifest['checks']}
    result = {'candidates': [candidate], 'expected_devloop_build': identity.get('build_id'),
              'expected_pid': identity.get('pid'), 'expected_run': identity.get('run'),
              'expected_revision': preparation.get('expected_revision'), 'retain_best': retain_best}
    from workbench.script_session import validate
    validate(**result)
    return result


def install_skill(destination=None, *, root=ROOT):
    source = Path(root) / 'skills/make-vita-app'
    codex_base = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    target = Path(destination) if destination else codex_base / 'skills/make-vita-app'
    if target.exists():
        raise FileExistsError('Skill destination already exists; review/update it explicitly')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    write_json(target / 'repository.json', {'repository': str(Path(root).resolve())})
    return {'result': 'installed', 'skill': str(target.resolve()), 'name': 'make-vita-app',
            'discovery': 'Start a fresh chat or refresh skills if the current client caches its catalog',
            'device_mutations': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('new', help='Create a private project without replacing existing work')
    new.add_argument('slug'); new.add_argument('--route', choices=ROUTES, required=True)
    new.add_argument('--name'); new.add_argument('--intent', default='')
    for name in ('inspect', 'check', 'build', 'session-args'):
        sub = commands.add_parser(name)
        sub.add_argument('slug')
        if name == 'build': sub.add_argument('--version', default='01.02')
        if name == 'session-args':
            sub.add_argument('preparation', type=Path)
            sub.add_argument('--duration', type=float, default=1.5)
            sub.add_argument('--retain-best', action='store_true')
    install = commands.add_parser('install-skill', help='Install a discoverable local skill; never overwrites')
    install.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.command == 'new': result = create(args.slug, args.route, args.name, args.intent)
    elif args.command == 'inspect':
        path, manifest = load(args.slug)
        result = {'project': str(path), 'manifest': manifest, 'device_mutations': 0}
    elif args.command == 'check': result = check_project(args.slug)
    elif args.command == 'build': result = build_project(args.slug, args.version)
    elif args.command == 'session-args':
        result = session_args(args.slug, read_json(args.preparation, 128 * 1024), args.duration, args.retain_best)
    else: result = install_skill(args.destination)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if result.get('result') in ('failed', 'blocked', 'failed_checks') else 0


if __name__ == '__main__':
    raise SystemExit(main())
