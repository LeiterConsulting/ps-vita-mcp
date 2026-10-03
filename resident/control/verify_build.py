"""Verify the two ARM modules as a matched pair and archive exact build inputs."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
from verify_build import ACCEPTED,elf,digest
from inspector.verify_build import authority,exports
sys.path.insert(0,str(ROOT/'scripts'))
from vita_artifacts import inspect
import zipfile
CORE=['kernel.c','lease.c','lease.h','api.h','http.c','platform_shell.c','control_platform.h','CMakeLists.txt','kernel.yml','shell.yml','bootstrap_metadata.c','bootstrap_probe.c','bootstrap_probe.yml','bootstrap_app.c','../platform.h','../sha256.c','../sha256.h']

def main(evidence):
    source=ROOT/'resident/control';native=ROOT/'build/resident/control';dist=ROOT/'dist/control'
    if evidence.parent.resolve()!=(ROOT/'evidence/control').resolve(): raise ValueError('Invalid build evidence directory')
    build_id=hashlib.sha256(''.join(digest(source/name) for name in CORE).encode()).hexdigest()
    report={'built_utc':datetime.now(timezone.utc).isoformat(),'version':'0.2.2','build_id':build_id,'modules':{},'source_hashes':{},'tests':{},'accepted_artifacts_preserved':{},'physical_acceptance':'pending: boot/load, cross-app capture, actual game input, file storage, no-input-after-expiry, app launch/return, screen latency and stability','evidence_directory':str(evidence)}
    for name,attributes,version,expected_imports in [
        ('vita_control',0,b'\x02\x00',{'SceIofilemgr','SceLibKernel','SceNet','SceNetCtl','ScePower','SceSysmodule','SceThreadmgr','SceAppMgrUser','VitaControlKernel'}),
        ('vita_control_kernel',0,b'\x01\x00',{'SceCtrlForDriver','SceThreadmgrForDriver','SceDisplayForDriver','SceSysmemForDriver','SceSysrootForDriver','SceSysclibForDriver','taihenForKernel'})]:
        extension='.skprx' if name.endswith('_kernel') else '.suprx'
        binary=(native/name).read_bytes();elf(binary,2)
        velf=(native/(name+'.velf')).read_bytes();sections=elf(velf,0xfe04);section=sections['.sceModuleInfo.rodata'];module=velf[section[4]:section[4]+section[5]]
        if len(module)!=92 or struct.unpack_from('<H',module)[0]!=attributes or module[2:4]!=version or module[4:31].split(b'\0')[0]!=name.encode() or not all(struct.unpack_from('<II',module,68)):
            raise ValueError('Unexpected module identity or lifecycle: '+name)
        imports=sorted(key.removeprefix('.text.fstubs.') for key in sections if key.startswith('.text.fstubs.'))
        if set(imports)!=expected_imports: raise ValueError('Unexpected imports: '+name+' '+str(imports))
        exported=exports(velf,sections)
        if exported[0]['name']!='main' or exported[0]['flags']!='8000': raise ValueError('Main exports missing')
        if name=='vita_control':
            if len(exported)!=1: raise ValueError('User module must not export kernel syscalls')
        elif len(exported)!=2 or exported[1]['name']!='VitaControlKernel' or exported[1]['flags']!='4001' or exported[1]['functions']!=7 or exported[1]['variables']:
            raise ValueError('Kernel syscall export table differs')
        if build_id.encode() not in binary or (native/(name+'-undefined.txt')).read_text().strip(): raise ValueError('Build fingerprint or unresolved symbols: '+name)
        payload=native/(name+extension)
        if payload.read_bytes()[:4]!=b'SCE\0' or not 0<payload.stat().st_size<256*1024: raise ValueError('Invalid SELF')
        authid=authority(payload.read_bytes())
        if authid!=(0x2f00000000000001 if name=='vita_control' else 0x2f00000000000002): raise ValueError('Incorrect SELF privilege flags: '+name)
        report['modules'][name]={'file':payload.name,'bytes':payload.stat().st_size,'sha256':digest(payload),'authid':f'{authid:016x}','exports':exported,'elf_sha256':digest(native/name),'velf_sha256':digest(native/(name+'.velf')),'imports':imports,'allocated_section_bytes':sum(s[5] for s in sections.values() if s[2]&2)}
        for suffix in ['', '.velf',extension,'-undefined.txt','-layout.txt']:
            shutil.copy2(native/(name+suffix),evidence/(name+suffix))
    app_imports={'taihenUnsafe','SceDisplayUser','SceDisplay','SceGxm','SceGxmInternalForVsh','SceSysmodule','SceCtrl','ScePgf','SceCommonDialog','SceSharedFb','SceAppMgrUser','SceIofilemgr','SceThreadmgr','SceRtcUser','SceSysmem','SceThreadmgrCoredumpTime','SceProcessmgr','SceLibKernel','SceNet'}
    for name,extension,expected_imports in [
        ('control_bootstrap_probe','.suprx',{'SceIofilemgr','SceLibKernel','SceThreadmgr','VitaControlKernel'}),
        ('control_starter','.self',app_imports)]:
        binary=(native/name).read_bytes();elf(binary,2)
        sections=elf((native/(name+'.velf')).read_bytes(),0xfe04);section=sections['.sceModuleInfo.rodata']
        module=(native/(name+'.velf')).read_bytes()[section[4]:section[4]+section[5]]
        if len(module)!=(144 if name=='control_starter' else 92) or module[4:31].split(b'\0')[0]!=name.encode(): raise ValueError('Unexpected starter module identity')
        if name=='control_starter' and module[96:100]!=b'PSP2': raise ValueError('Missing starter process parameters')
        if name=='control_bootstrap_probe' and (struct.unpack_from('<H',module)[0]!=0 or module[2:4]!=b'\x01\x00' or not all(struct.unpack_from('<II',module,68))): raise ValueError('Unexpected probe lifecycle')
        imports=sorted(key.removeprefix('.text.fstubs.') for key in sections if key.startswith('.text.fstubs.'))
        if set(imports)!=expected_imports: raise ValueError('Unexpected starter imports '+name+' '+str(imports))
        exported=exports((native/(name+'.velf')).read_bytes(),sections)
        if len(exported)!=1 or exported[0]['name']!='main' or exported[0]['flags']!='8000': raise ValueError('Starter modules must not re-export syscalls')
        undefined=(native/(name+'-undefined.txt')).read_text().splitlines()
        optional={'_ITM_deregisterTMCloneTable','_ITM_registerTMCloneTable','__deregister_frame_info','__libc_fini','__register_frame_info','_newlib_heap_size_user'}
        if name=='control_starter':
            if any(line.split()!=['w',line.split()[-1]] or line.split()[-1] not in optional for line in undefined): raise ValueError('Unresolved starter symbol')
        elif undefined: raise ValueError('Unresolved bootstrap probe symbol')
        payload=native/(name+extension)
        if build_id.encode() not in binary or authority(payload.read_bytes())!=0x2f00000000000001: raise ValueError('Starter fingerprint or unsafe SELF attributes differ')
        report['modules'][name]={'file':payload.name,'bytes':payload.stat().st_size,'sha256':digest(payload),'authid':'2f00000000000001','imports':imports,'exports':exported}
        for suffix in ['',extension,'.velf','-undefined.txt','-layout.txt']:shutil.copy2(native/(name+suffix),evidence/(name+suffix))
    package=inspect(native/'control_starter.vpk','Control Starter','CHRS00011','01.00')
    expected={'eboot.bin','sce_sys/param.sfo','sce_sys/icon0.png','sce_sys/livearea/contents/bg.png','sce_sys/livearea/contents/startup.png','sce_sys/livearea/contents/template.xml','vita_control_kernel.skprx','vita_control.suprx','control_bootstrap_probe.suprx','LICENSE.vitacompanion','LICENSE'}
    with zipfile.ZipFile(native/'control_starter.vpk') as archive:
        if set(archive.namelist())!=expected:raise ValueError('Unexpected starter package files')
        if archive.read('LICENSE')!=(ROOT/'LICENSE').read_bytes() or archive.read('LICENSE.vitacompanion')!=(source/'LICENSE.vitacompanion').read_bytes():raise ValueError('Starter license notices differ')
        for name in ['vita_control','vita_control_kernel','control_bootstrap_probe','control_starter']:
            info=report['modules'][name];entry='eboot.bin' if name=='control_starter' else info['file']
            if archive.read(entry)!=(native/info['file']).read_bytes():raise ValueError('Starter package contains a different native module')
    report['starter_package']=package
    report['runtime_activation']='manual foreground starter only; no boot configuration change or automatic activation'
    for relative in ACCEPTED:
        actual=digest(ROOT/relative)
        if actual!=ACCEPTED[relative]: raise ValueError('Previously accepted app changed')
        report['accepted_artifacts_preserved'][relative]=actual
    paths=list(source.glob('*'))+[ROOT/'resident/platform.h',ROOT/'resident/sha256.c',ROOT/'resident/sha256.h',ROOT/'resident/bridge.py',ROOT/'resident/inspector/verify_build.py',ROOT/'Build-Control.ps1',ROOT/'toolchain.lock.json',ROOT/'scripts/vita_artifacts.py',ROOT/'scripts/livearea_png.py',ROOT/'bridge/ftp_staging.py',ROOT/'resident/verify_build.py',ROOT/'assets/template.xml',ROOT/'tests/ftp_fixture.py']
    for path in paths:
        if path.is_file():
            relative=path.relative_to(ROOT);report['source_hashes'][relative.as_posix()]=digest(path)
            archived=evidence/'source'/relative;archived.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,archived)
    for name in ['host-tests.log','mcp-tests.log','resident-mcp-tests.log','staging-tests.log','native-build.log']:
        if not (evidence/name).stat().st_size: raise ValueError('Missing validation log')
        report['tests'][name]=digest(evidence/name)
    dist.mkdir(parents=True,exist_ok=True)
    for module in report['modules'].values(): shutil.copy2(native/module['file'],dist/module['file'])
    shutil.copy2(native/'control_starter.vpk',dist/'control_starter.vpk');shutil.copy2(native/'control_starter.vpk',evidence/'control_starter.vpk')
    for location in [evidence/'build-report.json',dist/'build-report.json']: location.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'build_id':build_id,'modules':report['modules'],'evidence':str(evidence),'device_acceptance':'pending'},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,required=True);main(parser.parse_args().evidence)
