"""Refresh exact source hashes in the two checked-in starting projects."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent/'projects'
for name,steps,checks in [
 ('smoke',[],[{'metric':'frames','min':60},{'metric':'seconds','min':1}]),
 ('input',[{'at_s':.5,'buttons':['right','cross'],'ttl_ms':800,'left_stick':[64,192],'right_stick':[192,64],'front_touch':[700,400],'rear_touch':[1300,700]}],[{'metric':'observed_mask','equals':31},{'metric':'held_frames','min':2},{'metric':'neutral_after','equals':1}])]:
    source=root/name/'main.lua';p={'name':'workbench_'+name,'source':'main.lua','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'duration_s':5,'warmup_s':.75,'steps':steps,'checks':checks}
    path=root/name/'trial.json';path.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8',newline='\n');print(name,hashlib.sha256(path.read_bytes()).hexdigest())
