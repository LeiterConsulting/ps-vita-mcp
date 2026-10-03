import argparse, hashlib, json, shutil, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
import struct
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'resident'))
sys.path.insert(0,str(ROOT/'scripts'))
from verify_build import ACCEPTED, digest, elf
from vita_artifacts import inspect
CORE=['api.h','kernel.c','kernel.yml','proxy.c','proxy.yml','app.c','CMakeLists.txt']

def authority(data):
    if len(data)<160 or data[:4]!=b'SCE\0': raise ValueError('Invalid SELF header')
    offset=struct.unpack_from('<Q',data,56)[0]
    if offset<128 or offset+32>len(data): raise ValueError('Invalid SELF app info')
    return struct.unpack_from('<Q',data,offset)[0]

def exports(data,sections):
    section=sections['.sceLib.ent']; table=data[section[4]:section[4]+section[5]]
    if not table or len(table)%32: raise ValueError('Invalid export table size')
    result=[]
    for pos in range(0,len(table),32):
        size,reserved,version,flags,functions,variables,tls,nid,name_pointer,nid_pointer,entry_pointer=struct.unpack_from('<BBHHHIIIIII',table,pos)
        if size!=32 or reserved or functions>64 or variables>64 or tls or not nid_pointer or not entry_pointer: raise ValueError('Invalid export descriptor')
        name='main'
        if name_pointer:
            found=False
            for region in sections.values():
                if region[1]!=8 and region[3]<=name_pointer<region[3]+region[5]:
                    offset=region[4]+name_pointer-region[3]
                    raw=data[offset:min(offset+64,region[4]+region[5])]
                    if b'\0' not in raw: raise ValueError('Unterminated export name')
                    name=raw.split(b'\0')[0].decode('ascii'); found=True; break
            if not found: raise ValueError('Export name pointer escaped sections')
        result.append({'name':name,'nid':f'{nid:08x}','flags':f'{flags:04x}','functions':functions,'variables':variables})
    return result

def main(evidence):
    native=ROOT/'build/resident/inspector'; source=ROOT/'resident/inspector'; dist=ROOT/'dist/inspector'
    if evidence.resolve().parent!=(ROOT/'evidence/control').resolve(): raise ValueError('Invalid inspector evidence directory')
    build_id=hashlib.sha256(''.join(digest(source/name) for name in CORE).encode()).hexdigest()
    report={'built_utc':datetime.now(timezone.utc).isoformat(),'build_id':build_id,'version':'01.03','modules':{},'source_hashes':{},'accepted_artifacts_preserved':{},'device_acceptance':'pending: launch, app metadata, optional Shell metadata, user proxy release, normal app exit; read-only syscall helper retained until reboot; not Control input/capture qualification'}
    allowed={
        'vi_kernel':{'SceSysrootForDriver','SceSysmemForDriver','SceThreadmgrForDriver','SceSysclibForDriver'},
        'vi_proxy':{'SceLibKernel','SceIofilemgr','SceThreadmgr','VitaInspectorKernel'},
        # The standard app CRT includes SceNet for its generic I/O adapter.
        # Inspector source opens no sockets and has no NetCtl dependency.
        'control_inspector':{'taihenUnsafe','SceDisplayUser','SceDisplay','SceGxm','SceGxmInternalForVsh','SceSysmodule','SceCtrl','ScePgf','SceCommonDialog','SceSharedFb','SceAppMgrUser','SceIofilemgr','SceThreadmgr','SceRtcUser','SceSysmem','SceThreadmgrCoredumpTime','SceProcessmgr','SceLibKernel','SceNet'},
    }
    for name,extension in [('vi_kernel','.skprx'),('vi_proxy','.suprx'),('control_inspector','.self')]:
        data=(native/name).read_bytes();elf(data,2)
        velf=(native/(name+'.velf')).read_bytes(); sections=elf(velf,0xfe04)
        section=sections['.sceModuleInfo.rodata']; module=velf[section[4]:section[4]+section[5]]
        expected_length=144 if name=='control_inspector' else 92
        if len(module)!=expected_length or module[4:31].split(b'\0')[0]!=name.encode(): raise ValueError('Wrong module identity: '+name)
        if name=='control_inspector' and module[96:100]!=b'PSP2': raise ValueError('App process parameters missing')
        imports=sorted(key.removeprefix('.text.fstubs.') for key in sections if key.startswith('.text.fstubs.'))
        exported=exports(velf,sections)
        if name=='vi_kernel':
            if len(exported)!=2 or exported[1]['name']!='VitaInspectorKernel' or exported[1]['flags']!='4001' or exported[1]['functions']!=4 or exported[1]['variables']:
                raise ValueError('Unexpected kernel exports')
        elif len(exported)!=1: raise ValueError('User modules must not re-export helper syscalls')
        if exported[0]['name']!='main' or exported[0]['flags']!='8000': raise ValueError('Main export missing')
        if set(imports)!=allowed[name]: raise ValueError('Unexpected diagnostic imports: '+name+' '+str(imports))
        if name!='control_inspector':
            if set(imports)!=allowed[name] or struct.unpack_from('<H',module)[0]!=0 or module[2:4]!=b'\x01\x00' or not all(struct.unpack_from('<II',module,68)):
                raise ValueError('Unexpected diagnostic lifecycle/imports: '+name+' '+str(imports))
        elif 'VitaInspectorKernel' in imports: raise ValueError('App must launch without helper imports')
        undefined=(native/(name+'-undefined.txt')).read_text().splitlines()
        crt_optional={'_ITM_deregisterTMCloneTable','_ITM_registerTMCloneTable','__deregister_frame_info','__libc_fini','__register_frame_info','_newlib_heap_size_user'}
        if name=='control_inspector':
            if any(line.split()!=['w',line.split()[-1]] or line.split()[-1] not in crt_optional for line in undefined): raise ValueError('Unexpected unresolved app symbol')
        elif undefined: raise ValueError('Unexpected unresolved module symbol')
        if build_id.encode() not in data: raise ValueError('Fingerprint failure: '+name)
        payload=native/(name+extension)
        if payload.read_bytes()[:4]!=b'SCE\0' or not 0<payload.stat().st_size<1024*1024: raise ValueError('Invalid SELF')
        authid=authority(payload.read_bytes())
        if authid!=(0x2f00000000000002 if name=='vi_kernel' else 0x2f00000000000001): raise ValueError('Kernel/user SELF privilege flags leaked between modules')
        report['modules'][name]={'file':payload.name,'bytes':payload.stat().st_size,'sha256':digest(payload),'authid':f'{authid:016x}','imports':imports,'exports':exported,'allocated_section_bytes':sum(s[5] for s in sections.values() if s[2]&2)}
        for suffix in ['',extension,'.velf','-undefined.txt','-layout.txt']: shutil.copy2(native/(name+suffix),evidence/(name+suffix))
    package=inspect(native/'control_inspector.vpk','Control Inspector','CHRS00010','01.03')
    expected={'eboot.bin','sce_sys/param.sfo','sce_sys/icon0.png','sce_sys/livearea/contents/bg.png','sce_sys/livearea/contents/startup.png','sce_sys/livearea/contents/template.xml','vi_kernel.skprx','vi_proxy.suprx'}
    with zipfile.ZipFile(native/'control_inspector.vpk') as archive:
        if set(archive.namelist())!=expected: raise ValueError('Unexpected VPK files')
        for name,extension in [('vi_kernel','.skprx'),('vi_proxy','.suprx'),('control_inspector','.self')]:
            if archive.read('eboot.bin' if name=='control_inspector' else name+extension)!=(native/(name+extension)).read_bytes(): raise ValueError('VPK contains different module bytes')
    report['package']=package
    for relative,expected_hash in ACCEPTED.items():
        observed=digest(ROOT/relative)
        if observed!=expected_hash: raise ValueError('Accepted artifact changed')
        report['accepted_artifacts_preserved'][relative]=observed
    for path in [*source.glob('*'),ROOT/'Build-Inspector.ps1',ROOT/'toolchain.lock.json',ROOT/'scripts/vita_artifacts.py',ROOT/'scripts/livearea_png.py',ROOT/'bridge/ftp_staging.py',ROOT/'resident/verify_build.py',ROOT/'assets/template.xml',ROOT/'tests/ftp_fixture.py']:
        if path.is_file():
            relative=path.relative_to(ROOT); report['source_hashes'][relative.as_posix()]=digest(path)
            saved=evidence/'source'/relative;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
    for leaf in ['kernel-tests.log','proxy-tests.log','native-build.log']:
        if not (evidence/leaf).stat().st_size: raise ValueError('Validation log missing')
    report['toolchain']=json.loads((ROOT/'toolchain.lock.json').read_text())
    report['evidence_directory']=str(evidence)
    dist.mkdir(exist_ok=True,parents=True)
    shutil.copy2(native/'control_inspector.vpk',dist/'control_inspector.vpk');shutil.copy2(native/'control_inspector.vpk',evidence/'control_inspector.vpk')
    for path in [dist/'build-report.json',evidence/'build-report.json']:path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'package':package,'modules':report['modules'],'build_id':build_id,'device_acceptance':'pending','evidence_directory':str(evidence)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,required=True);main(parser.parse_args().evidence)
