/* Actual immutable store/core with bounded simulated persisted IO. The actual
   POSIX service/HTTP fixture supplies independent real-filesystem coverage. */
#include "store.h"
#include "../sha256.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct { int exists;size_t size;unsigned char bytes[LB_STORE_WIRE_BYTES+1]; } DiskFile;
static DiskFile disk[LB_STORE_CAPACITY+2][3];
static int root_exists,root_directory=1,fd_sequence,fd_kind,fd_writing;
static size_t fd_offset;
static int fail_open,fail_write,fail_read,fail_file_sync,fail_device_sync,fail_close,fail_stat,fail_mkdir,corrupt_read;
static unsigned write_calls,launches,assertions;
static int write_error_after=-1;
static uint64_t now=2000;
static unsigned fault_after_launch;
static uint64_t advance_on_sync;
#define REQUIRE(value) do {assert(value);assertions++;} while(0)

static int consume(int *value) {int result=*value;*value=0;return result;}
static DiskFile *file(const char *name,int *sequence,int *kind) {
    unsigned number;char suffix[8]={0},trailing;
    int n=sscanf(name,LB_STORE_ROOT "/record-%u%7s%c",&number,suffix,&trailing);
    assert(n==2&&number>=1&&number<=LB_STORE_CAPACITY+1);
    int type=!strcmp(suffix,".bin")?0:!strcmp(suffix,".part")?1:!strcmp(suffix,".tmp")?2:-1;
    assert(type>=0);if(sequence)*sequence=(int)number;if(kind)*kind=type;
    return &disk[number][type];
}
int r_pair_exists(const char *name) {
    if(consume(&fail_stat))return -1;
    if(!strcmp(name,LB_STORE_ROOT))return root_exists;
    return file(name,0,0)->exists;
}
int r_directory_exists(const char *name) {assert(!strcmp(name,LB_STORE_ROOT));return root_exists&&root_directory;}
int r_dir(const char *name) {assert(!strcmp(name,LB_STORE_ROOT));if(consume(&fail_mkdir)||root_exists)return -1;root_exists=1;return 0;}
int r_file_size(const char *name,uint64_t *size) {DiskFile *f=file(name,0,0);if(!f->exists)return -1;*size=f->size;return 0;}
int r_open_write(const char *name) {
    if(consume(&fail_open))return -1;
    DiskFile *f=file(name,&fd_sequence,&fd_kind);if(f->exists)return -1;
    f->exists=1;fd_writing=1;fd_offset=0;return 10;
}
int r_open_read(const char *name) {
    if(consume(&fail_open))return -1;
    DiskFile *f=file(name,&fd_sequence,&fd_kind);if(!f->exists)return -1;
    fd_writing=0;fd_offset=0;return 10;
}
int r_write(int fd,const void *data,size_t size) {
    assert(fd==10&&fd_writing);write_calls++;
    if(consume(&fail_write)||(write_error_after>=0&&(int)write_calls>write_error_after))return -1;
    DiskFile *f=&disk[fd_sequence][fd_kind];if(size>19)size=19;
    assert(fd_offset+size<=sizeof(f->bytes));memcpy(f->bytes+fd_offset,data,size);fd_offset+=size;f->size=fd_offset;return (int)size;
}
int r_read(int fd,void *data,size_t size) {
    assert(fd==10&&!fd_writing);if(consume(&fail_read))return -1;
    DiskFile *f=&disk[fd_sequence][fd_kind];if(size>f->size-fd_offset)size=f->size-fd_offset;if(size>17)size=17;
    memcpy(data,f->bytes+fd_offset,size);fd_offset+=size;
    if(size&&consume(&corrupt_read))((unsigned char *)data)[0]^=1;
    return (int)size;
}
int r_close_file(int fd) {assert(fd==10);return consume(&fail_close)?-1:0;}
int r_pair_sync_file(int fd) {
    assert(fd==10&&fd_writing);
    if(advance_on_sync){now=advance_on_sync;advance_on_sync=0;}
    return consume(&fail_file_sync)?-1:0;
}
int r_pair_sync_device(void) {return consume(&fail_device_sync)?-1:0;}
static uint64_t clock_ms(void *ctx) {(void)ctx;return now;}
static LBLaunchResult launch(void *ctx) {
    (void)ctx;launches++;
    if(fault_after_launch==1)fail_write=1;
    if(fault_after_launch==2)fail_file_sync=1;
    if(fault_after_launch==3)fail_device_sync=1;
    if(fault_after_launch==4)corrupt_read=1;
    LBLaunchResult result={1,0};return result;
}
static LBAdapter adapter={clock_ms,lb_store_recover_last,lb_store_claim,lb_store_save,lb_store_lookup,launch};

static void reset(void) {
    memset(disk,0,sizeof(disk));root_exists=0;root_directory=1;
    fail_open=fail_write=fail_read=fail_file_sync=fail_device_sync=fail_close=fail_stat=fail_mkdir=corrupt_read=0;
    write_calls=launches=fault_after_launch=0;write_error_after=-1;advance_on_sync=0;now=2000;
}
static LBReceipt queued(unsigned attempt) {
    LBReceipt r={0};r.format=LB_FORMAT;r.state=LB_QUEUED;r.native_result=-1;
    snprintf(r.attempt,sizeof(r.attempt),"%032x",attempt);strcpy(r.title,LB_TITLE);
    strcpy(r.resident_build,R_BUILD_ID);memset(r.instance,'b',32);memset(r.devloop_build,'d',64);
    r.issued_ms=1000;r.expires_ms=6000;r.accepted_ms=2000;return r;
}
static LBConfig config(const LBReceipt *r) {
    LBConfig c={0};strcpy(c.resident_build,r->resident_build);strcpy(c.instance,r->instance);c.enabled=1;return c;
}
static LBRequest request(const LBReceipt *r) {
    LBRequest q={0};q.auth.role=LB_ROLE_ADMIN;strcpy(q.auth.resident_build,r->resident_build);strcpy(q.auth.instance,r->instance);
    strcpy(q.attempt,r->attempt);strcpy(q.title,r->title);strcpy(q.devloop_build,r->devloop_build);q.issued_ms=r->issued_ms;q.ttl_ms=5000;return q;
}
static LBReceipt dispatch(LBReceipt r) {r.state=LB_DISPATCH_INTENT;r.dispatch_count=1;r.dispatch_ms=2100;return r;}
static LBReceipt submitted(LBReceipt r) {r.state=LB_SUBMITTED;r.native_confirmed=1;r.native_result=0;return r;}
static LBReceipt observed(LBReceipt r,unsigned samples,uint64_t frame) {
    r.samples=samples;r.state=samples==2?LB_OBSERVED:LB_SUBMITTED;
    strcpy(r.observation.title,LB_TITLE);strcpy(r.observation.version,"01.04");strcpy(r.observation.build,r.devloop_build);
    memset(r.observation.run,'e',32);r.observation.pid=123;r.observation.frame=frame;r.observation.revision=7;r.observation.paused=1;
    return r;
}
static void checksum(DiskFile *f) {RSha h;char digest[65];rs_init(&h);rs_update(&h,f->bytes,LB_STORE_WIRE_BYTES-64);rs_final(&h,digest);memcpy(f->bytes+LB_STORE_WIRE_BYTES-64,digest,64);}
static void little32(unsigned char *p,uint32_t value) {for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(value>>(8*i));}

static void basic_and_transitions(void) {
    reset();LBStore s;LBReceipt out,r=queued(1);REQUIRE(lb_store_init(&s)==0&&root_exists);
    REQUIRE(lb_store_recover_last(&s,&out)==0);REQUIRE(lb_store_lookup(&s,r.attempt,&out)==1);
    REQUIRE(lb_store_claim(&s,&r)==0&&s.count==1&&s.attempt_count==1);
    REQUIRE(lb_store_claim(&s,&r)==1&&s.count==1);
    LBReceipt fresh=queued(2);REQUIRE(lb_store_claim(&s,&fresh)==1);
    REQUIRE(lb_store_lookup(&s,r.attempt,&out)==0&&out.state==LB_QUEUED);
    LBReceipt wrong=submitted(dispatch(r));REQUIRE(lb_store_save(&s,&wrong)<0&&s.count==1);
    LBReceipt d=dispatch(r);REQUIRE(lb_store_save(&s,&d)==0);
    wrong=d;wrong.dispatch_ms++;REQUIRE(lb_store_save(&s,&wrong)<0);
    LBReceipt n=submitted(d);wrong=observed(n,1,10);REQUIRE(lb_store_save(&s,&wrong)<0);
    REQUIRE(lb_store_save(&s,&n)==0);
    wrong=n;wrong.native_result=3;REQUIRE(lb_store_save(&s,&wrong)<0);
    wrong=observed(n,2,11);REQUIRE(lb_store_save(&s,&wrong)<0);
    LBReceipt one=observed(n,1,10);REQUIRE(lb_store_save(&s,&one)==0);
    LBReceipt two=observed(one,2,11);wrong=two;wrong.observation.frame=10;REQUIRE(lb_store_save(&s,&wrong)<0);
    wrong=two;wrong.observation.pid++;REQUIRE(lb_store_save(&s,&wrong)<0);
    wrong=two;wrong.observation.run[0]='f';REQUIRE(lb_store_save(&s,&wrong)<0);
    wrong=two;wrong.observation.revision++;REQUIRE(lb_store_save(&s,&wrong)<0);
    REQUIRE(lb_store_save(&s,&two)==0);
    REQUIRE(lb_store_claim(&s,&fresh)==0);
    REQUIRE(lb_store_lookup(&s,r.attempt,&out)==0&&out.state==LB_OBSERVED&&out.samples==2);
    LBStore rebuilt;REQUIRE(lb_store_init(&rebuilt)==0&&rebuilt.count==6&&rebuilt.attempt_count==2);
    REQUIRE(lb_store_lookup(&rebuilt,r.attempt,&out)==0&&out.state==LB_OBSERVED);
    REQUIRE(lb_store_claim(&rebuilt,&r)==1);
}

static void restart_and_no_replay(void) {
    for(unsigned phase=0;phase<3;phase++) {
        reset();LBStore s;LBReceipt r=queued(1),out;LBConfig c=config(&r);LBRequest q=request(&r);LBCore core;
        REQUIRE(lb_store_init(&s)==0&&lb_init(&core,&c,&adapter,&s)==LB_OK);
        REQUIRE(lb_offer(&core,&q,&out)==LB_ACCEPTED);
        if(phase) {now=2100;REQUIRE(lb_dispatch_after_response(&core,r.attempt,phase==2,&out)==LB_OK);}
        unsigned old_launches=launches;
        LBStore rebuilt;LBCore new_core;REQUIRE(lb_store_init(&rebuilt)==0);
        REQUIRE(lb_init(&new_core,&c,&adapter,&rebuilt)==LB_OK&&launches==old_launches);
        REQUIRE(new_core.current.state==LB_UNKNOWN&&new_core.current.reason==LB_REASON_RESTART);
        REQUIRE(lb_dispatch_after_response(&new_core,r.attempt,1,&out)==LB_CONFLICT&&launches==old_launches);
        LBReceipt next=queued(2);q=request(&next);REQUIRE(lb_offer(&new_core,&q,&out)==LB_CONFLICT);
        c.instance[0]='c';REQUIRE(lb_init(&new_core,&c,&adapter,&rebuilt)==LB_OK&&launches==old_launches);
        q.auth.instance[0]='c';now=2200;REQUIRE(lb_offer(&new_core,&q,&out)==LB_ACCEPTED);
        q=request(&r);q.auth.instance[0]='c';REQUIRE(lb_offer(&new_core,&q,&out)==LB_CONFLICT);
    }
    reset();LBStore s;LBReceipt r=queued(1),out;LBConfig c=config(&r);LBCore core;
    REQUIRE(lb_store_init(&s)==0&&lb_init(&core,&c,&adapter,&s)==LB_OK);
    LBRequest q=request(&r);REQUIRE(lb_offer(&core,&q,&out)==LB_ACCEPTED);
    now=6000;REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_OK&&out.state==LB_EXPIRED&&launches==0);
}

static void io_faults(void) {
    for(unsigned fault=0;fault<8;fault++) {
        reset();LBStore s;LBReceipt r=queued(1),out;REQUIRE(lb_store_init(&s)==0);
        if(fault==0)fail_open=1;
        if(fault==1)fail_write=1;
        if(fault==2)write_error_after=1;
        if(fault==3)fail_file_sync=1;
        if(fault==4)fail_close=1;
        if(fault==5)fail_device_sync=1;
        if(fault==6)fail_read=1;
        if(fault==7)corrupt_read=1;
        REQUIRE(lb_store_claim(&s,&r)<0&&s.blocked&&launches==0);
        REQUIRE(lb_store_claim(&s,&r)<0&&lb_store_recover_last(&s,&out)<0);
        write_error_after=-1;
        LBStore rebuilt;int recovered=lb_store_init(&rebuilt);
        if(fault==1||fault==2)REQUIRE(recovered<0&&rebuilt.blocked);
        else {
            REQUIRE(recovered==0);
            LBConfig c=config(&r);LBCore core;REQUIRE(lb_init(&core,&c,&adapter,&rebuilt)==LB_OK&&launches==0);
            if(fault!=0)REQUIRE(core.current.state==LB_UNKNOWN);
        }
    }
    reset();LBStore s;fail_stat=1;REQUIRE(lb_store_init(&s)<0&&s.blocked);
    reset();fail_mkdir=1;REQUIRE(lb_store_init(&s)<0&&s.blocked);
    reset();fail_device_sync=1;REQUIRE(lb_store_init(&s)<0&&s.blocked);
    reset();root_exists=1;root_directory=0;REQUIRE(lb_store_init(&s)<0&&s.blocked);
}

static void forged_records_and_drift(void) {
    for(unsigned forged=0;forged<11;forged++) {
        reset();LBStore s;LBReceipt r=queued(1);REQUIRE(lb_store_init(&s)==0&&lb_store_claim(&s,&r)==0);
        DiskFile *f=&disk[1][0];
        if(forged==0)f->bytes[0]^=1;
        if(forged==1)little32(f->bytes+8,2);
        if(forged==2)little32(f->bytes+12,2);
        if(forged==3)f->bytes[16]='f';
        if(forged==4)f->bytes[80]=2;
        if(forged==5)f->bytes[84]=LB_SUBMITTED;
        if(forged==6)f->bytes[133]='f'; /* wrong compiled Resident build */
        if(forged==7)f->bytes[341]='X'; /* noncanonical unused observation */
        if(forged==8)f->bytes[LB_STORE_WIRE_BYTES-1]^=1;
        if(forged==9)f->size--;
        if(forged==10)f->size++;
        if(forged<8)checksum(f);
        LBStore rebuilt;REQUIRE(lb_store_init(&rebuilt)<0&&rebuilt.blocked);
    }
    reset();LBStore s;LBReceipt r=queued(1),out;REQUIRE(lb_store_init(&s)==0&&lb_store_claim(&s,&r)==0);
    LBStore rival;REQUIRE(lb_store_init(&rival)==0);LBReceipt cancelled=r;cancelled.state=LB_CANCELLED;cancelled.reason=LB_REASON_DISABLED;
    REQUIRE(lb_store_save(&rival,&cancelled)==0);
    REQUIRE(lb_store_recover_last(&s,&out)<0&&s.blocked);
    reset();REQUIRE(lb_store_init(&s)==0&&lb_store_claim(&s,&r)==0);
    disk[1][0].bytes[100]^=1;REQUIRE(lb_store_lookup(&s,r.attempt,&out)<0&&s.blocked);
    reset();REQUIRE(lb_store_init(&s)==0);r.resident_build[0]='f';REQUIRE(lb_store_claim(&s,&r)<0&&s.count==0);
    for(unsigned kind=0;kind<3;kind++) {
        reset();root_exists=1;disk[2][kind].exists=1;LBStore orphan;
        REQUIRE(lb_store_init(&orphan)<0&&orphan.blocked);
    }
    reset();root_exists=1;disk[LB_STORE_CAPACITY+1][0].exists=1;REQUIRE(lb_store_init(&s)<0);
}

static void dispatch_and_completion_faults(void) {
    for(unsigned phase=0;phase<2;phase++)for(unsigned fault=1;fault<=4;fault++) {
        reset();LBStore s;LBReceipt r=queued(1),out;LBConfig c=config(&r);LBRequest q=request(&r);LBCore core;
        REQUIRE(lb_store_init(&s)==0&&lb_init(&core,&c,&adapter,&s)==LB_OK);
        REQUIRE(lb_offer(&core,&q,&out)==LB_ACCEPTED);
        if(phase)fault_after_launch=fault;
        else {
            if(fault==1)fail_write=1;
            if(fault==2)fail_file_sync=1;
            if(fault==3)fail_device_sync=1;
            if(fault==4)write_error_after=(int)write_calls+1;
        }
        now=2100;
        REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_UNAVAILABLE);
        REQUIRE(core.blocked&&out.state==LB_UNKNOWN&&out.reason==LB_REASON_STORAGE);
        REQUIRE(launches==phase);
        REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_UNAVAILABLE&&launches==phase);
        write_error_after=-1;fault_after_launch=0;
        LBStore rebuilt;int recovered=lb_store_init(&rebuilt);
        if((!phase&&(fault==1||fault==4))||(phase&&fault==1))REQUIRE(recovered<0&&rebuilt.blocked);
        else {
            REQUIRE(recovered==0);
            LBCore fresh;REQUIRE(lb_init(&fresh,&c,&adapter,&rebuilt)==LB_OK&&launches==phase);
            REQUIRE(fresh.current.state==LB_UNKNOWN&&fresh.current.reason==LB_REASON_RESTART);
            REQUIRE(lb_dispatch_after_response(&fresh,r.attempt,1,&out)==LB_CONFLICT&&launches==phase);
        }
    }
    reset();LBStore s;LBReceipt r=queued(1),out;LBConfig c=config(&r);LBRequest q=request(&r);LBCore core;
    REQUIRE(lb_store_init(&s)==0&&lb_init(&core,&c,&adapter,&s)==LB_OK);
    REQUIRE(lb_offer(&core,&q,&out)==LB_ACCEPTED);
    now=2100;advance_on_sync=6000;
    REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_OK&&out.state==LB_EXPIRED&&launches==0);
    LBStore rebuilt;REQUIRE(lb_store_init(&rebuilt)==0);
    REQUIRE(lb_store_recover_last(&rebuilt,&out)==1&&out.state==LB_EXPIRED&&out.dispatch_count==1);

    reset();REQUIRE(lb_store_init(&s)==0&&lb_init(&core,&c,&adapter,&s)==LB_OK);
    REQUIRE(lb_offer(&core,&q,&out)==LB_ACCEPTED);
    now=2100;REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_OK&&launches==1);
    LBObservation o=observed(core.current,1,10).observation;
    REQUIRE(lb_observe(&core,&q.auth,r.attempt,&o,&out)==LB_OK&&out.samples==1);
    now=2099;uint64_t sampled;
    REQUIRE(lb_status_clock(&core,&sampled)==LB_UNAVAILABLE&&core.blocked&&core.current.samples==0);
    REQUIRE(lb_store_init(&rebuilt)==0);
    REQUIRE(lb_store_recover_last(&rebuilt,&out)==1&&out.state==LB_UNKNOWN&&out.reason==LB_REASON_CLOCK&&out.samples==0);
    REQUIRE(lb_dispatch_after_response(&core,r.attempt,1,&out)==LB_UNAVAILABLE&&launches==1);
}

static void capacity_and_terminal_paths(void) {
    reset();LBStore s;REQUIRE(lb_store_init(&s)==0);
    for(unsigned i=1;i<=LB_STORE_CAPACITY/2;i++) {
        LBReceipt r=queued(i);REQUIRE(lb_store_claim(&s,&r)==0);
        r.state=LB_CANCELLED;r.reason=LB_REASON_DISABLED;REQUIRE(lb_store_save(&s,&r)==0);
    }
    REQUIRE(s.count==LB_STORE_CAPACITY&&s.attempt_count==LB_STORE_CAPACITY/2);
    LBReceipt next=queued(99);REQUIRE(lb_store_claim(&s,&next)<0&&s.blocked);
    LBStore rebuilt;REQUIRE(lb_store_init(&rebuilt)==0&&rebuilt.count==LB_STORE_CAPACITY);
    LBReceipt out;next=queued(1);REQUIRE(lb_store_lookup(&rebuilt,next.attempt,&out)==0&&out.state==LB_CANCELLED);
    REQUIRE(lb_store_claim(&rebuilt,&next)==1);
    next=queued(99);REQUIRE(lb_store_claim(&rebuilt,&next)<0&&rebuilt.blocked);
    for(unsigned terminal=0;terminal<4;terminal++) {
        reset();LBReceipt r=queued(1);REQUIRE(lb_store_init(&s)==0&&lb_store_claim(&s,&r)==0);
        if(terminal<3) {r=dispatch(r);REQUIRE(lb_store_save(&s,&r)==0);}
        if(terminal==0) {r.state=LB_NATIVE_REJECTED;r.native_confirmed=1;r.native_result=-10;}
        if(terminal==1) {r.state=LB_EXPIRED;r.reason=LB_REASON_EXPIRY;}
        if(terminal==2) {r.state=LB_UNKNOWN;r.reason=LB_REASON_NATIVE;}
        if(terminal==3) {r.state=LB_UNKNOWN;r.reason=LB_REASON_RESPONSE;}
        REQUIRE(lb_store_save(&s,&r)==0&&lb_store_init(&rebuilt)==0);
        REQUIRE(lb_store_recover_last(&rebuilt,&out)==1&&out.state==r.state);
    }
}

int main(void) {
    basic_and_transitions();restart_and_no_replay();io_faults();forged_records_and_drift();
    dispatch_and_completion_faults();capacity_and_terminal_paths();
    printf("launch store/core: %u assertions passed (bounded persisted IO, no native SDK)\n",assertions);
    return 0;
}
