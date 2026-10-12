#include "store.h"
#include "../platform.h"
#include "../sha256.h"
#include <limits.h>

enum { RECORD_CLAIM=1,RECORD_SAVE=2, CHECKSUM_OFFSET=LB_STORE_WIRE_BYTES-64 };
static int equal(const void *a,const void *b,size_t n) {
    const unsigned char *x=a,*y=b;unsigned difference=0;
    for(size_t i=0;i<n;i++)difference|=(unsigned)(x[i]^y[i]);
    return difference==0;
}
static int hex(const char *s,unsigned n) {
    for(unsigned i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return s[n]==0;
}
static void path(char out[96],unsigned sequence,const char *suffix) {
    R_SNPRINTF(out,96,LB_STORE_ROOT "/record-%03u%s",sequence,suffix);
}
static void put32(unsigned char **p,uint32_t value) {
    for(unsigned i=0;i<4;i++)*(*p)++=(unsigned char)(value>>(i*8));
}
static void put64(unsigned char **p,uint64_t value) {
    for(unsigned i=0;i<8;i++)*(*p)++=(unsigned char)(value>>(i*8));
}
static uint32_t get32(const unsigned char **p) {
    uint32_t value=0;for(unsigned i=0;i<4;i++)value|=(uint32_t)*(*p)++<<(i*8);return value;
}
static uint64_t get64(const unsigned char **p) {
    uint64_t value=0;for(unsigned i=0;i<8;i++)value|=(uint64_t)*(*p)++<<(i*8);return value;
}
static int32_t signed32(uint32_t value) {
    return value<=INT32_MAX?(int32_t)value:-1-(int32_t)(UINT32_MAX-value);
}
static void put_text(unsigned char **p,const char *text,size_t n) {R_MEMCPY(*p,text,n);*p+=n;}
static void get_text(const unsigned char **p,char *text,size_t n) {R_MEMCPY(text,*p,n);text[n]=0;*p+=n;}
static void digest(const unsigned char *wire,char out[65]) {
    RSha hash;rs_init(&hash);rs_update(&hash,wire,CHECKSUM_OFFSET);rs_final(&hash,out);
}
static void encode(unsigned char wire[LB_STORE_WIRE_BYTES],unsigned sequence,unsigned kind,const char previous[65],const LBReceipt *r) {
    unsigned char *p=wire;LBObservation zero={0};const LBObservation *o=r->samples?&r->observation:&zero;
    put_text(&p,"VLBSTR01",8);put32(&p,sequence);put32(&p,kind);put_text(&p,previous,64);
    put32(&p,r->format);put32(&p,(uint32_t)r->state);put32(&p,(uint32_t)r->reason);
    put_text(&p,r->attempt,32);put_text(&p,r->title,9);put_text(&p,r->resident_build,64);
    put_text(&p,r->instance,32);put_text(&p,r->devloop_build,64);
    put64(&p,r->issued_ms);put64(&p,r->expires_ms);put64(&p,r->accepted_ms);put64(&p,r->dispatch_ms);
    put32(&p,r->dispatch_count);put32(&p,(uint32_t)r->native_confirmed);put32(&p,(uint32_t)r->native_result);put32(&p,r->samples);
    put_text(&p,o->title,9);put_text(&p,o->version,5);put_text(&p,o->build,64);put_text(&p,o->run,32);
    put32(&p,(uint32_t)o->pid);put64(&p,o->frame);put64(&p,o->revision);put32(&p,(uint32_t)o->paused);put32(&p,(uint32_t)o->faulted);
    char hash[65];digest(wire,hash);put_text(&p,hash,64);
}
static int receipt_valid(const LBReceipt *r) {
    if(!lb_receipt_valid(r)||!hex(R_BUILD_ID,64)||R_STRCMP(r->resident_build,R_BUILD_ID)||
       r->accepted_ms-r->issued_ms>LB_MAX_AGE_MS)return 0;
    if(!r->dispatch_count && (r->dispatch_ms||r->native_confirmed||r->native_result!=-1||r->samples))return 0;
    if(r->dispatch_count && (r->dispatch_ms<r->accepted_ms||r->dispatch_ms>=r->expires_ms))return 0;
    if((r->state==LB_QUEUED||r->state==LB_DISPATCH_INTENT||r->state==LB_SUBMITTED||r->state==LB_NATIVE_REJECTED||r->state==LB_OBSERVED)&&r->reason!=LB_REASON_NONE)return 0;
    if(r->state==LB_QUEUED)return !r->dispatch_count;
    if(r->state==LB_DISPATCH_INTENT)return !r->native_confirmed&&r->native_result==-1&&!r->samples;
    if(r->state==LB_SUBMITTED)return r->samples<=1;
    if(r->state==LB_EXPIRED)return r->reason==LB_REASON_EXPIRY&&!r->native_confirmed&&r->native_result==-1;
    if(r->state==LB_CANCELLED)return r->reason==LB_REASON_DISABLED&&!r->dispatch_count;
    if(r->state==LB_UNKNOWN) {
        if(r->reason==LB_REASON_RESTART||r->reason==LB_REASON_STORAGE||r->reason==LB_REASON_CLOCK)return 1;
        if(r->reason==LB_REASON_RESPONSE)return !r->dispatch_count;
        if(r->reason==LB_REASON_NATIVE)return r->dispatch_count&&!r->native_confirmed;
        return r->reason==LB_REASON_OBSERVATION&&r->dispatch_count&&r->native_confirmed&&r->native_result>=0;
    }
    return r->state==LB_NATIVE_REJECTED||r->state==LB_OBSERVED;
}
static int decode(const unsigned char wire[LB_STORE_WIRE_BYTES],unsigned sequence,const char previous[65],unsigned *kind,LBReceipt *r,char hash[65]) {
    const unsigned char *p=wire;R_MEMSET(r,0,sizeof(*r));
    if(!equal(p,"VLBSTR01",8))return -1;
    p+=8;
    if(get32(&p)!=sequence)return -1;
    *kind=get32(&p);
    if((*kind!=RECORD_CLAIM&&*kind!=RECORD_SAVE)||!equal(p,previous,64))return -1;
    p+=64;
    r->format=get32(&p);uint32_t state=get32(&p),reason=get32(&p);
    if(state>LB_CANCELLED||reason>LB_REASON_OBSERVATION)return -1;
    r->state=(LBState)state;r->reason=(LBReason)reason;
    get_text(&p,r->attempt,32);get_text(&p,r->title,9);get_text(&p,r->resident_build,64);
    get_text(&p,r->instance,32);get_text(&p,r->devloop_build,64);
    r->issued_ms=get64(&p);r->expires_ms=get64(&p);r->accepted_ms=get64(&p);r->dispatch_ms=get64(&p);
    r->dispatch_count=get32(&p);uint32_t confirmed=get32(&p);r->native_result=signed32(get32(&p));r->samples=get32(&p);
    if(confirmed>1)return -1;
    r->native_confirmed=(int)confirmed;
    get_text(&p,r->observation.title,9);get_text(&p,r->observation.version,5);get_text(&p,r->observation.build,64);get_text(&p,r->observation.run,32);
    r->observation.pid=signed32(get32(&p));r->observation.frame=get64(&p);r->observation.revision=get64(&p);
    uint32_t paused=get32(&p),faulted=get32(&p);if(paused>1||faulted>1)return -1;
    r->observation.paused=(int)paused;r->observation.faulted=(int)faulted;
    digest(wire,hash);if(!equal(p,hash,64)||!receipt_valid(r))return -1;
    /* Re-encode to reject noncanonical unused observation bytes. */
    unsigned char canonical[LB_STORE_WIRE_BYTES];encode(canonical,sequence,*kind,previous,r);
    return equal(wire,canonical,sizeof(canonical))?0:-1;
}
static int same_intent(const LBReceipt *a,const LBReceipt *b) {
    return a->format==b->format&&equal(a->attempt,b->attempt,33)&&equal(a->title,b->title,10)&&
        equal(a->resident_build,b->resident_build,65)&&equal(a->instance,b->instance,33)&&
        equal(a->devloop_build,b->devloop_build,65)&&a->issued_ms==b->issued_ms&&
        a->expires_ms==b->expires_ms&&a->accepted_ms==b->accepted_ms;
}
static int transition(const LBReceipt *a,const LBReceipt *b) {
    if(!receipt_valid(b)||!same_intent(a,b))return 0;
    if(b->state==LB_DISPATCH_INTENT) return a->state==LB_QUEUED&&a->dispatch_count==0&&b->dispatch_count==1;
    if(a->dispatch_count!=b->dispatch_count||a->dispatch_ms!=b->dispatch_ms)return 0;
    int native_equal=a->native_confirmed==b->native_confirmed&&a->native_result==b->native_result;
    if(b->state==LB_UNKNOWN&&(b->reason==LB_REASON_RESTART||b->reason==LB_REASON_CLOCK))return native_equal;
    if(a->state==LB_QUEUED)return b->state==LB_CANCELLED||b->state==LB_EXPIRED||
        (b->state==LB_UNKNOWN&&b->reason==LB_REASON_RESPONSE);
    if(a->state==LB_DISPATCH_INTENT)return !b->samples&&
        (b->state==LB_SUBMITTED||b->state==LB_NATIVE_REJECTED||b->state==LB_EXPIRED||
         (b->state==LB_UNKNOWN&&b->reason==LB_REASON_NATIVE));
    if(a->state!=LB_SUBMITTED||!native_equal)return 0;
    if(b->state==LB_UNKNOWN)return b->reason==LB_REASON_OBSERVATION;
    if(!((a->samples==0&&b->samples==1&&b->state==LB_SUBMITTED)||
         (a->samples==1&&b->samples==2&&b->state==LB_OBSERVED)))return 0;
    return !a->samples||(a->observation.pid==b->observation.pid&&equal(a->observation.run,b->observation.run,33)&&
        a->observation.revision==b->observation.revision&&a->observation.frame<b->observation.frame);
}
static int read_wire(const char *name,unsigned char wire[LB_STORE_WIRE_BYTES]) {
    uint64_t size;if(r_file_size(name,&size)<0||size!=LB_STORE_WIRE_BYTES)return -1;
    int fd=r_open_read(name);if(fd<0)return -1;size_t used=0;int ok=1;
    while(used<LB_STORE_WIRE_BYTES) {int n=r_read(fd,wire+used,LB_STORE_WIRE_BYTES-used);if(n<=0||(size_t)n>LB_STORE_WIRE_BYTES-used){ok=0;break;}used+=(unsigned)n;}
    unsigned char extra;if(ok&&r_read(fd,&extra,1)!=0)ok=0;
    if(r_close_file(fd)<0)ok=0;
    return ok?0:-1;
}
static int can_claim(const LBStore *s,const LBReceipt *r) {
    if(!receipt_valid(r)||r->state!=LB_QUEUED)return 0;
    for(unsigned i=0;i<s->attempt_count;i++)if(equal(s->attempts[i],r->attempt,33))return 0;
    return !s->count||(s->latest.state!=LB_QUEUED&&s->latest.state!=LB_DISPATCH_INTENT&&
        (s->latest.state!=LB_UNKNOWN||!equal(s->latest.instance,r->instance,33)));
}
/* Scan all slots, including after an absent slot. Reject owned-name orphans. */
static int scan(LBStore *s,const char *wanted,LBReceipt *found,int *matched) {
    char previous[65];R_MEMSET(previous,'0',64);previous[64]=0;s->count=0;s->attempt_count=0;
    int gap=0;if(matched)*matched=0;
    for(unsigned i=1;i<=LB_STORE_CAPACITY+1;i++) {
        char name[96];path(name,i,".part");if(r_pair_exists(name)!=0)return -1;
        path(name,i,".tmp");if(r_pair_exists(name)!=0)return -1;
        path(name,i,".bin");int exists=r_pair_exists(name);if(exists<0)return -1;
        if(!exists){gap=1;continue;}
        if(gap||i>LB_STORE_CAPACITY)return -1;
        unsigned char wire[LB_STORE_WIRE_BYTES];LBReceipt next;unsigned kind;char hash[65];
        if(read_wire(name,wire)<0||decode(wire,i,previous,&kind,&next,hash)<0)return -1;
        if(kind==RECORD_CLAIM) {
            if(!can_claim(s,&next))return -1;
            R_MEMCPY(s->attempts[s->attempt_count++],next.attempt,33);
        } else if(!s->count||!transition(&s->latest,&next))return -1;
        s->latest=next;s->count=i;R_MEMCPY(previous,hash,65);
        if(wanted&&equal(wanted,next.attempt,33)){*found=next;*matched=1;}
    }
    R_MEMCPY(s->digest,previous,65);return 0;
}
static int check(LBStore *s,const char *wanted,LBReceipt *found,int *matched) {
    if(!s||!s->initialized||s->blocked)return -1;
    LBStore current={0};
    if(!r_directory_exists(LB_STORE_ROOT)||scan(&current,wanted,found,matched)<0||current.count!=s->count||
       !equal(current.digest,s->digest,65)){s->blocked=1;return -1;}
    return 0;
}
int lb_store_init(LBStore *s) {
    if(!s)return -1;
    R_MEMSET(s,0,sizeof(*s));s->initialized=1;
    int exists=r_pair_exists(LB_STORE_ROOT);
    if(exists<0||(!exists&&(r_dir(LB_STORE_ROOT)<0||r_pair_sync_device()<0))||
       !r_directory_exists(LB_STORE_ROOT)||scan(s,0,0,0)<0){s->blocked=1;return -1;}
    return 0;
}
int lb_store_recover_last(void *ctx,LBReceipt *out) {
    LBStore *s=ctx;if(!out||check(s,0,0,0)<0)return -1;
    if(!s->count)return 0;
    *out=s->latest;return 1;
}
static int append(LBStore *s,unsigned kind,const LBReceipt *r) {
    if(s->count>=LB_STORE_CAPACITY){s->blocked=1;return -1;}
    unsigned char wire[LB_STORE_WIRE_BYTES],readback[LB_STORE_WIRE_BYTES];char name[96];
    unsigned sequence=s->count+1;encode(wire,sequence,kind,s->digest,r);path(name,sequence,".bin");
    int fd=r_open_write(name);if(fd<0){s->blocked=1;return -1;}
    size_t used=0;int ok=1;
    while(used<sizeof(wire)) {int n=r_write(fd,wire+used,sizeof(wire)-used);if(n<=0||(size_t)n>sizeof(wire)-used){ok=0;break;}used+=(unsigned)n;}
    if(ok&&r_pair_sync_file(fd)<0)ok=0;
    if(r_close_file(fd)<0)ok=0;
    if(ok&&r_pair_sync_device()<0)ok=0;
    if(!ok||read_wire(name,readback)<0||!equal(wire,readback,sizeof(wire))){s->blocked=1;return -1;}
    s->count=sequence;s->latest=*r;if(!r->samples)R_MEMSET(&s->latest.observation,0,sizeof(s->latest.observation));
    digest(wire,s->digest);
    if(kind==RECORD_CLAIM)R_MEMCPY(s->attempts[s->attempt_count++],r->attempt,33);
    return 0;
}
int lb_store_claim(void *ctx,const LBReceipt *r) {
    LBStore *s=ctx;if(!r||check(s,0,0,0)<0)return -1;
    if(!receipt_valid(r)||r->state!=LB_QUEUED)return -1;
    if(!can_claim(s,r))return 1;
    return append(s,RECORD_CLAIM,r);
}
int lb_store_save(void *ctx,const LBReceipt *r) {
    LBStore *s=ctx;if(!r||check(s,0,0,0)<0||!s->count||!transition(&s->latest,r))return -1;
    return append(s,RECORD_SAVE,r);
}
int lb_store_lookup(void *ctx,const char attempt[33],LBReceipt *out) {
    LBStore *s=ctx;int matched=0;
    if(!attempt||!out||!hex(attempt,32)||check(s,attempt,out,&matched)<0)return -1;
    return matched?0:1;
}
