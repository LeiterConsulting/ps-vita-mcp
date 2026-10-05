"""Refuse private phone source, credentials and generated evidence in tracked files."""
from pathlib import Path, PurePosixPath
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIRS = {'.devloop-private', 'companion', 'iphone', 'ios', 'vitacompanioncore',
                'build', 'dist', 'evidence', 'previews', 'outgoing', '.venv', '.venv-devloop', '.codex'}
PRIVATE_SUFFIXES = {'.swift', '.m', '.mm', '.storyboard', '.xib', '.entitlements', '.xcconfig',
                    '.pbxproj', '.ipa', '.mobileprovision', '.p12', '.p8',
                    '.vpk', '.velf', '.self', '.elf', '.suprx', '.skprx', '.pyc', '.pyo'}

def private_path(path):
    p = PurePosixPath(path.lower())
    if any(part in PRIVATE_DIRS or part.endswith(('.xcodeproj', '.xcworkspace', '.xcarchive', '.xcassets')) for part in p.parts):
        return True
    if p.suffix in PRIVATE_SUFFIXES or p.name == 'companion.zip' or ('machandoff' in p.name and p.suffix == '.zip'):
        return True
    return p.name == '.env' or p.name.startswith('.env.') and p.name != '.env.example'

def self_test():
    denied = ['companion/VitaCompanionCore/Package.swift', 'Sources/App.swift', 'Sources/Phone.mm',
              'Resources/Phone.storyboard', 'Resources/Phone.xcassets/icon.png', 'Phone.xcodeproj/project.pbxproj',
              'Phone.xcworkspace/contents.xcworkspacedata', 'phone.ipa', 'Phone.xcarchive/Info.plist',
              'Signing/profile.mobileprovision', '.devloop-private/resident.json', '.env.local',
              'evidence/workbench/report.json', 'companion.zip', 'VitaCompanion-MacHandoff.zip']
    allowed = ['docs/IPHONE-COMPANION.md', 'docs/PAIRING.md', 'resident/pairing.c', 'resident/pairing.h',
               'tools/pairing_check.py', '.env.example', 'scripts/check_public_scope.py']
    assert all(private_path(path) for path in denied)
    assert not any(private_path(path) for path in allowed)

def main():
    self_test()
    raw = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT)
    files = [p.decode('utf-8') for p in raw.split(b'\0') if p]
    denied = [p for p in files if private_path(p)]
    if denied:
        # Report filenames only. Never read or echo a private file's contents.
        print(json.dumps({'result': 'FAIL', 'private_tracked_paths': denied}, indent=2))
        return 1
    print(json.dumps({'result': 'PASS', 'tracked_files': len(files), 'private_phone_or_runtime_paths': 0,
                      'scope': 'Tracked path audit; not a credential-content scan or history audit'}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
