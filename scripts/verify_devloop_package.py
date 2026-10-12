"""Verify the independent DevLoop package without modifying earlier test-app artifacts."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import struct
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from livearea_png import validate_livearea_png
from devloop_identity import verify_native_identity
ROOT = Path(__file__).resolve().parents[1]
def digest(path):
    with path.open("rb") as source: return hashlib.file_digest(source, "sha256").hexdigest()
def sfo(data):
    magic, version, key_start, data_start, count = struct.unpack_from("<5I", data)
    assert magic == 0x46535000 and version == 0x101
    result = {}
    for n in range(count):
        key_offset, fmt, length, maximum, value_offset = struct.unpack_from("<HHIII", data, 20+n*16)
        key = data[key_start+key_offset:].split(b"\0",1)[0].decode()
        value = data[data_start+value_offset:data_start+value_offset+length]
        assert length <= maximum and len(value) == length
        result[key] = struct.unpack_from("<I",value)[0] if fmt == 0x404 else value.rstrip(b"\0").decode()
    return result
build = ROOT / "build/devloop"
elf = build / "vita_devloop"
elf_data = elf.read_bytes()
native_build_id,native_sources = verify_native_identity(ROOT,build)
assert b"CHRS00003" in elf_data and b"01.04" in elf_data
assert elf_data[:6] == b"\x7fELF\x01\x01" and struct.unpack_from("<H",elf_data,18)[0] == 40
self_data=(build/'vita_devloop.self').read_bytes()
assert self_data[:4]==b'SCE\0'
image=json.loads((ROOT/'toolchain.lock.json').read_text())['image']
chain=subprocess.run(['docker','run','--rm','--network','none','--mount',f'type=bind,source={ROOT},target=/workspace',image,'sh','scripts/verify_devloop_chain.sh'],cwd=ROOT,capture_output=True,text=True,timeout=600)
chain_log=ROOT/'evidence/devloop/elf-self-chain.log';chain_log.parent.mkdir(parents=True,exist_ok=True)
chain_log.write_text(chain.stdout+chain.stderr,encoding='utf-8')
if chain.returncode:raise RuntimeError('Current ELF/SELF conversion differs; see '+str(chain_log))
package = build / "vita_devloop.vpk"
with zipfile.ZipFile(package) as archive:
    assert archive.testzip() is None
    names = archive.namelist()
    assert len(names) == len(set(names)) and all(not p.startswith(("/","\\")) and ".." not in Path(p).parts for p in names)
    assert len(names) == 7 and archive.read("licenses.txt") == (ROOT/"assets/devloop-licenses.txt").read_bytes()
    assert archive.read("eboot.bin") == self_data
    metadata = sfo(archive.read("sce_sys/param.sfo"))
    assert metadata["TITLE_ID"] == "CHRS00003" and metadata["TITLE"] == "Vita DevLoop"
    assert metadata["APP_VER"] == "01.04" and metadata["CATEGORY"] == "gd" and metadata["PSP2_SYSTEM_VER"] <= 0x03650000
    profiles = {name: validate_livearea_png(archive.read(name),size) for name,size in (("sce_sys/icon0.png",(128,128)),("sce_sys/livearea/contents/bg.png",(840,500)),("sce_sys/livearea/contents/startup.png",(280,158)))}
    template = ET.fromstring(archive.read("sce_sys/livearea/contents/template.xml"))
    assert template.tag == "livearea" and template.attrib["style"] == "a1"
    assert template.find("livearea-background/image").text == "bg.png" and template.find("gate/startup-image").text == "startup.png"
    unpacked = sum(entry.file_size for entry in archive.infolist())
dist = ROOT / "dist/devloop"
dist.mkdir(parents=True,exist_ok=True)
target = dist / package.name
shutil.copy2(package,target)
assert digest(package) == digest(target)
sources = {}
for folder in ("common","devloop","bridge","assets/vita_devloop","experiments","third_party/lua-5.4.9"):
    for path in sorted((ROOT/folder).rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts: sources[path.relative_to(ROOT).as_posix()] = digest(path)
for name in ("apps/vita_devloop.c","CMakeLists.txt","Build-DevLoop.ps1","Stage-DevLoop.ps1","Setup-DevLoop.ps1","README.md","SCRIPTING.md","ROADMAP.md","LICENSE","THIRD_PARTY_NOTICES.md","docs/SETUP.md","docs/VALIDATION.md","scripts/generate_devloop_assets.py","scripts/devloop_identity.cmake","scripts/devloop_identity.py","scripts/verify_devloop_package.py","scripts/verify_devloop_chain.sh","scripts/test_devloop.sh","scripts/build_host_lua.sh","scripts/fetch_lua.py","scripts/check_publication_regression.py","tests/test_devloop_identity.py","tests/test_devloop.c","tests/test_script_runtime.c","tests/render_stub.c","tests/test_bridge.py","tests/test_scripts_bridge.py","tests/test_ftp_staging.py","tests/ftp_fixture.py","tests/test_server_vita_host.c","tests/server_host_shim.h","assets/template.xml","toolchain.lock.json"):
    sources[name] = digest(ROOT/name)
sources["assets/devloop-licenses.txt"] = digest(ROOT/"assets/devloop-licenses.txt")
report = {"builtUtc": datetime.now(timezone.utc).isoformat(), "toolchain": json.loads((ROOT/"toolchain.lock.json").read_text()), "lua": json.loads((ROOT/"third_party/lua-5.4.9/provenance.json").read_text()), "package": {"file": target.name, "titleId": "CHRS00003", "version": "01.04", "buildId":native_build_id, "bytes": target.stat().st_size, "unpackedBytes": unpacked, "sha256": digest(target), "elfSha256": digest(elf), "velfSha256":digest(build/"vita_devloop.velf"), "selfSha256":digest(build/"vita_devloop.self"), "sfo": metadata, "liveareaPngProfiles": profiles}, "nativeIdentity": {"buildId":native_build_id,"sourceHashes":native_sources,"format":"SHA-256 of sorted relative-path:SHA-256 LF records; exact native inputs and toolchain lock; session run is clock/PID correlation, not authentication"}, "sourceHashes": sources, "conversionVerification": {"image":image,"command":"sh scripts/verify_devloop_chain.sh","logSha256":digest(chain_log)}, "verification": "Canonical native source fingerprint, ARM ELF, independent ELF-to-SELF byte equality, exact VPK executable, ZIP CRC, firmware/SFO and indexed opaque LiveArea artwork", "physicalAcceptance": "pending: identity PID/captured foreground and run/build continuity, installation, live Lua Wi-Fi MCP calls, framebuffer, exit and sleep/return"}
(dist/"build-report.json").write_text(json.dumps(report,indent=2)+"\n")
(dist/"SHA256SUMS.txt").write_text(digest(target)+"  vita_devloop.vpk\n")
print(f"PASS independent DevLoop VPK: CHRS00003, 01.04, {target.stat().st_size:,} bytes; SHA-256 {digest(target)}")
