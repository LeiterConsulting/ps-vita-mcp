"""Validated immutable package staging through the boot-resident service."""
import hashlib,json,re,uuid,zipfile
from .runner import Device,Journal,ROOT,utc
from .session import exclusive
def candidate(package,expected_sha256,root=ROOT):
    if package not in ('starter','target') or not re.fullmatch('[0-9a-f]{64}',expected_sha256):raise ValueError('Choose starter or target with its exact build-report hash')
    base=root/('dist/control' if package=='starter' else 'dist/workbench')
    report=json.loads((base/'build-report.json').read_text())
    info=report['starter_package' if package=='starter' else 'package'];payload=(base/('control_starter.vpk' if package=='starter' else 'input_target.vpk')).read_bytes()
    identity=('CHRS00011','01.04') if package=='starter' else ('CHRS00012','01.00')
    if (info['titleId'],info['version'])!=identity or info['sha256']!=expected_sha256 or hashlib.sha256(payload).hexdigest()!=expected_sha256 or len(payload)!=info['bytes'] or not 0<len(payload)<2*1024*1024:raise ValueError('Candidate package identity differs')
    if package=='starter' and report['version']!='0.3.3':raise ValueError('Unexpected Control release')
    for relative,digest in {**report['source_hashes'],**report['accepted_artifacts_preserved']}.items():
        source=(root/relative).resolve()
        if root.resolve() not in source.parents or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise ValueError('Candidate source or accepted artifact drift')
    with zipfile.ZipFile(base/('control_starter.vpk' if package=='starter' else 'input_target.vpk')) as a:
        if a.testzip() is not None or set(a.namelist())!={f['name'] for f in info['files']}:raise ValueError('Candidate ZIP layout differs')
        for f in info['files']:
            data=a.read(f['name'])
            if len(data)!=f['bytes'] or hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('Candidate package content differs')
    return payload,{'package':package,'title_id':identity[0],'version':identity[1],'build_id':report['build_id'],'sha256':expected_sha256,'bytes':len(payload)}
def stage(package,expected_sha256,device=None,root=ROOT):
    payload,identity=candidate(package,expected_sha256,root);d=device or Device()
    with exclusive():
        j=Journal(root,'candidate-stage');attempt=uuid.uuid4().hex;j.report.update(identity);j.report['attempt']=attempt;j.save()
        try:
            d.resident.vita_resident_status()
            receipt=j.mutation('publish_native_candidate',{'attempt':attempt,'file':'package.vpk',**identity},lambda:d.resident.upload(payload,'package.vpk',attempt))
            j.report['receipt']=receipt;j.report['result']='verified staged candidate; installation and runtime pending'
        except Exception as error:
            j.report['result']='failed or publication uncertain; inspect this attempt without replay';j.report['failure_type']=type(error).__name__
        j.report['activation']='not performed';j.report['finished_utc']=utc();j.save()
        return {**j.report,'evidence_directory':str(j.folder)}
