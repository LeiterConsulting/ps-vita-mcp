"""Canonical native DevLoop source identity, excluding generated output and PC code."""
import hashlib
from pathlib import Path


def native_inputs(root):
    names = (root / 'devloop/build-inputs.txt').read_text(encoding='utf-8').splitlines()
    lua = root / 'third_party/lua-5.4.9/src'
    excluded = {'lua.c', 'luac.c', 'linit.c', 'ldblib.c', 'liolib.c', 'loslib.c', 'loadlib.c', 'lcorolib.c'}
    names += [path.relative_to(root).as_posix() for path in lua.iterdir()
              if path.suffix == '.h' or path.suffix == '.c' and path.name not in excluded]
    names += [path.relative_to(root).as_posix() for folder in ('apps','common','devloop') for path in (root/folder).rglob('*.h')]
    if len(names)!=len(set(names)):raise ValueError('Duplicate native fingerprint input')
    names = sorted(names)
    if any(not name or Path(name).is_absolute() or '..' in Path(name).parts for name in names):
        raise ValueError('Invalid native fingerprint input')
    return names


def native_identity(root):
    sources = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in native_inputs(root)}
    manifest = ''.join(f'{name}:{digest}\n' for name, digest in sources.items())
    return hashlib.sha256(manifest.encode('ascii')).hexdigest(), sources, manifest


def verify_native_identity(root, build):
    identity, sources, manifest = native_identity(root)
    if (build / 'devloop-native-inputs.sha256').read_text(encoding='utf-8') != manifest:
        raise ValueError('Native DevLoop inputs differ; reconfigure and rebuild')
    if (build / 'devloop_build_identity.h').read_text(encoding='utf-8') != f'#define DEV_BUILD_ID "{identity}"\n':
        raise ValueError('Generated native DevLoop build identity differs')
    if identity.encode('ascii') not in (build / 'vita_devloop').read_bytes():
        raise ValueError('Native ELF lacks the exact source identity')
    return identity, sources
