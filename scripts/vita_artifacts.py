"""Read-only artifact helpers for independent Vita components."""
import hashlib
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bridge'))
from ftp_staging import read_sfo, PACKAGE_FILES
from livearea_png import validate_livearea_png


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect(path, title, title_id, version):
    if not 0 < path.stat().st_size < 2 * 1024 * 1024:
        raise ValueError('Inspector package size is outside its bound')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not PACKAGE_FILES.issubset(names):
            raise ValueError('Missing or duplicate package entries')
        if any(name.startswith(('/', '\\')) or '\\' in name or '..' in name.split('/') for name in names):
            raise ValueError('Package entry escapes its layout')
        if sum(item.file_size for item in archive.infolist()) > 4 * 1024 * 1024 or archive.testzip() is not None:
            raise ValueError('Invalid package size or ZIP CRC')
        if archive.read('eboot.bin')[:4] != b'SCE\0':
            raise ValueError('Invalid app SELF')
        metadata = read_sfo(archive.read('sce_sys/param.sfo'))
        if metadata.get('TITLE') != title or metadata.get('TITLE_ID') != title_id or metadata.get('APP_VER') != version or metadata.get('CATEGORY') != 'gd' or type(metadata.get('PSP2_SYSTEM_VER')) is not int or metadata['PSP2_SYSTEM_VER'] > 0x03650000:
            raise ValueError('Package title, version or firmware differs')
        profiles = {name: validate_livearea_png(archive.read(name), size) for name, size in (
            ('sce_sys/icon0.png', (128, 128)),
            ('sce_sys/livearea/contents/bg.png', (840, 500)),
            ('sce_sys/livearea/contents/startup.png', (280, 158)),
        )}
        template = ET.fromstring(archive.read('sce_sys/livearea/contents/template.xml'))
        if template.tag != 'livearea' or template.attrib.get('style') != 'a1' or template.findtext('livearea-background/image') != 'bg.png' or template.findtext('gate/startup-image') != 'startup.png':
            raise ValueError('Unexpected LiveArea template')
        files = [{'name': name, 'bytes': len(archive.read(name)), 'sha256': hashlib.sha256(archive.read(name)).hexdigest()} for name in names]
    return {'file': path.name, 'title': title, 'titleId': title_id, 'version': version,
            'bytes': path.stat().st_size, 'sha256': digest(path), 'files': files,
            'liveareaPngProfiles': profiles, 'packageValidation': 'passed', 'installedRuntime': 'pending'}
