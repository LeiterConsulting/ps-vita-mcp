#include "autostart.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define BUILD "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
typedef struct {
    uint64_t now,first_load,cancel_at;
    int armed,guards,claim,verify,kernel,probe,release,service,start_status;
    int claims,verifications,kernels,probes,releases,services,guard_reads,ready_reads;
    int guard_race,unstable,rollback,cancel_after_verify;
    AOProbe metadata;
} Fixture;
static uint64_t now(void *p) { return ((Fixture *)p)->now; }
static int running(void *p) { Fixture *f=p;return !f->cancel_at || f->now<f->cancel_at; }
static void delay(void *p,unsigned value) { Fixture *f=p;f->now+=value;if(f->rollback && f->now==1000)f->now=100; }
static int armed(void *p) { return ((Fixture *)p)->armed; }
static int ready(void *p) { Fixture *f=p;f->ready_reads++;return f->unstable==2 ? 0 : !(f->unstable==1 && f->ready_reads==3); }
static int guards(void *p) { Fixture *f=p;f->guard_reads++;return f->guard_race && f->guard_reads==2 ? 0 : f->guards; }
static int claim(void *p) { Fixture *f=p;assert(!f->kernels && !f->probes && !f->services);f->claims++;return f->claim; }
static int verify(void *p) { Fixture *f=p;assert(f->claims==1);f->verifications++;if(f->cancel_after_verify)f->cancel_at=f->now;return f->verify; }
static int kernel(void *p) { Fixture *f=p;assert(f->claims==1 && f->verifications==1 && !f->kernels);f->kernels++;f->first_load=f->now;return f->kernel; }
static AOProbe probe(void *p) { Fixture *f=p;assert(f->kernels==1 && !f->probes);f->probes++;AOProbe out=f->metadata;out.module_id=f->probe;return out; }
static int release(void *p,int id) { Fixture *f=p;assert(f->probes==1 && id==f->probe && !f->releases);f->releases++;return f->release; }
static int service(void *p,int *status) { Fixture *f=p;assert(f->releases==1 && !f->services);f->services++;*status=f->start_status;return f->service; }
static void event(void *p,AOState state,int code) { (void)p;(void)state;(void)code; }
static const AOPlatform platform={now,running,delay,armed,ready,guards,claim,verify,kernel,probe,release,service,event};
static Fixture fresh(void) {
    Fixture f={.armed=1,.guards=1,.kernel=41,.probe=42,.service=43};
    f.metadata=(AOProbe){.module_id=42,.info={.magic=RC_BOOT_MAGIC,.abi=RC_ABI,.size=112,.ready=1,.caller_before=84,.caller_after=84,.shell_pid=84,.guard_allowed=1}};
    memcpy(f.metadata.info.build_id,BUILD,65);return f;
}
static AOResult run(Fixture *f,AOState wanted) { AOResult result=ao_run(&platform,f,84,BUILD);assert(result.state==wanted && !result.network_verified);return result; }
int main(void) {
    Fixture f=fresh();AOResult result=run(&f,AO_MODULES_SUBMITTED);
    assert(result.claimed && result.kernel_id==41 && result.probe_id==42 && result.service_id==43);
    assert(f.first_load==16000 && f.kernels==1 && f.probes==1 && f.releases==1 && f.services==1);
    assert(strstr(ao_state_name(result.state),"network unverified"));
    f=fresh();f.armed=0;run(&f,AO_DISABLED);assert(!f.claims && !f.kernels);
    f=fresh();f.armed=-10;run(&f,AO_DISABLED);assert(!f.claims);
    f=fresh();f.guards=-1;run(&f,AO_GUARD_BLOCKED);assert(!f.claims);
    f=fresh();f.guard_race=1;run(&f,AO_GUARD_BLOCKED);assert(!f.claims && !f.kernels);
    f=fresh();f.cancel_at=1000;run(&f,AO_CANCELLED);assert(!f.claims);
    f=fresh();f.unstable=2;run(&f,AO_READINESS_TIMEOUT);assert(f.now==120000 && !f.claims);
    f=fresh();f.rollback=1;run(&f,AO_READINESS_TIMEOUT);assert(!f.claims);
    f=fresh();f.unstable=1;run(&f,AO_MODULES_SUBMITTED);assert(f.first_load==17500);
    f=fresh();f.claim=-3;run(&f,AO_CLAIM_FAILED);assert(!f.kernels && !f.verifications);
    f=fresh();f.verify=-4;result=run(&f,AO_FILES_REJECTED);assert(result.claimed && !f.kernels);
    f=fresh();f.cancel_after_verify=1;run(&f,AO_CANCELLED);assert(!f.kernels);
    f=fresh();f.kernel=-5;run(&f,AO_KERNEL_FAILED);assert(f.kernels==1 && !f.probes && !f.releases);
    f=fresh();f.probe=-6;run(&f,AO_PROBE_FAILED);assert(f.kernels==1 && f.probes==1 && !f.releases && !f.services);
    f=fresh();f.release=-7;run(&f,AO_PROBE_RELEASE_FAILED);assert(!f.services);
    f=fresh();f.service=-8;run(&f,AO_SERVICE_FAILED);assert(f.services==1);
    f=fresh();f.start_status=-9;run(&f,AO_SERVICE_FAILED);assert(f.services==1);
    f=fresh();f.now=50000;run(&f,AO_MODULES_SUBMITTED);assert(f.first_load==51000);
    f=fresh();assert(ao_run(&platform,&f,0,BUILD).state==AO_GUARD_BLOCKED && !f.claims);
    for(unsigned field=0;field<13;field++) {
        f=fresh();
        switch(field) {
            case 0:f.metadata.start_result=-1;break;
            case 1:f.metadata.metadata_result=-1;break;
            case 2:f.metadata.info.magic=0;break;
            case 3:f.metadata.info.abi++;break;
            case 4:f.metadata.info.size--;break;
            case 5:f.metadata.info.ready=0;break;
            case 6:f.metadata.info.caller_before=83;break;
            case 7:f.metadata.info.caller_after=83;break;
            case 8:f.metadata.info.shell_pid=83;break;
            case 9:f.metadata.info.guard_allowed=0;break;
            case 10:f.metadata.info.build_id[64]='x';break;
            case 11:f.metadata.info.build_id[0]='f';break;
            case 12:f.metadata.info.padding[6]=1;break;
        }
        run(&f,AO_METADATA_REJECTED);assert(f.kernels==1 && f.releases==1 && !f.services);
    }
    puts("PASS: actual one-shot core, 32 state/metadata cases; no native SDK execution.");
    return 0;
}
