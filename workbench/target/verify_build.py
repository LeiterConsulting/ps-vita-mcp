"""Verify the standalone test app identity, SELF authority, source fingerprint and accepted artifacts."""
from pathlib import Path
import hashlib,json,shutil,struct,sys,zipfile
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from resident.verify_build import elf,ACCEPTED,digest
from resident.inspector.verify_build import authority,exports
sys.path.insert(0,str(ROOT/'scripts'))
from vita_artifacts import inspect
CORE=['main.c','telemetry.c','telemetry.h','protocol.c','protocol.h','server.c','platform_vita.c','CMakeLists.txt','../../common/platform.h','../../common/math_helpers.c','../../common/math_helpers.h']
def verify(evidence):
    source=ROOT/'workbench/target';native=ROOT/'build/workbench/target';dist=ROOT/'dist/workbench'
    fingerprint=hashlib.sha256(''.join(digest(source/name) for name in CORE).encode()).hexdigest()
    binary=(native/'input_target').read_bytes();elf(binary,2)
    velf=(native/'input_target.velf').read_bytes();sections=elf(velf,0xfe04)
    section=sections['.sceModuleInfo.rodata'];module=velf[section[4]:section[4]+section[5]]
    if len(module)!=144 or module[4:31].split(b'\0')[0]!=b'input_target' or module[96:100]!=b'PSP2':raise ValueError('Input Target process identity differs')
    exported=exports(velf,sections)
    if len(exported)!=1 or exported[0]['flags']!='8000' or exported[0]['name']!='main':raise ValueError('Unexpected test app exports')
    payload=(native/'input_target.self').read_bytes()
    if fingerprint.encode() not in binary or authority(payload)!=0x2f00000000000001:raise ValueError('Test app fingerprint or SELF authority differs')
    undefined=(native/'undefined.txt').read_text().splitlines()
    optional={'_ITM_deregisterTMCloneTable','_ITM_registerTMCloneTable','__deregister_frame_info','__libc_fini','__register_frame_info','_newlib_heap_size_user'}
    if any(line.split()!=['w',line.split()[-1]] or line.split()[-1] not in optional for line in undefined):raise ValueError('Unresolved app symbol')
    package=inspect(native/'input_target.vpk','Vita Input Target','CHRS00012','01.00')
    with zipfile.ZipFile(native/'input_target.vpk') as a:
        expected={'eboot.bin','LICENSE','sce_sys/param.sfo','sce_sys/icon0.png','sce_sys/livearea/contents/bg.png','sce_sys/livearea/contents/startup.png','sce_sys/livearea/contents/template.xml'}
        if a.read('eboot.bin')!=payload or set(a.namelist())!=expected:raise ValueError('Unexpected test app package')
    report={'built_utc':datetime.now(timezone.utc).isoformat(),'build_id':fingerprint,'package':package,'source_hashes':{},'accepted_artifacts_preserved':{},'physical_acceptance':'pending: launch, both touch panels, additive stick delivery, expiry, self exit and suspend/wake'}
    for relative,expected in ACCEPTED.items():
        if digest(ROOT/relative)!=expected:raise ValueError('Previously accepted app changed')
        report['accepted_artifacts_preserved'][relative]=expected
    evidence.mkdir(parents=True,exist_ok=True);dist.mkdir(parents=True,exist_ok=True)
    for path in [*(source/name for name in CORE),*source.rglob('*.png'),source/'artwork.py',source/'verify_build.py',source/'test_host.sh',source/'test_target.c']:
        path=path.resolve();relative=path.relative_to(ROOT);report['source_hashes'][relative.as_posix()]=digest(path);out=evidence/'source'/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out)
    for name in ['input_target','input_target.velf','input_target.self','input_target.vpk','undefined.txt']:shutil.copy2(native/name,evidence/name)
    for name in ['build-report.json']:(evidence/name).write_text(json.dumps(report,indent=2)+'\n');(dist/name).write_text(json.dumps(report,indent=2)+'\n')
    shutil.copy2(native/'input_target.vpk',dist/'input_target.vpk');print(json.dumps({'build_id':fingerprint,'package_sha256':package['sha256'],'bytes':package['bytes'],'evidence':str(evidence),'device_acceptance':'pending'},indent=2))
if __name__=='__main__':verify(Path(sys.argv[1]))
