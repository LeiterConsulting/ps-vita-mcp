#include "launch_broker.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define BUILD "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
#define DEVBUILD "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
#define INSTANCE "0123456789abcdef0123456789abcdef"
#define NEXT_INSTANCE "abcdef0123456789abcdef0123456789"
typedef struct {
    LBReceipt records[16];unsigned count,last;
    uint64_t now,claim_advance,save_advance,launch_advance;
    int recover_error,claim_error,claim_partial,save_fail_at,save_partial,lookup_error;
    int claim_calls,save_calls,lookup_calls,launch_calls;
    LBLaunchResult launch_result;
} Fake;
static Fake f;
static LBCore c;
static LBConfig config;
static LBAdapter adapter;
static LBRequest request;
static LBReceipt receipt;
static unsigned cases;

static uint64_t now_ms(void *ctx) { return ((Fake *)ctx)->now; }
static int recover(void *ctx,LBReceipt *out) {
    Fake *p=ctx;if(p->recover_error)return -1;
    if(!p->count)return 0;
    *out=p->records[p->last];return 1;
}
static int claim(void *ctx,const LBReceipt *r) {
    Fake *p=ctx;++p->claim_calls;assert(lb_receipt_valid(r));
    for(unsigned i=0;i<p->count;i++)if(!strcmp(p->records[i].attempt,r->attempt))return 1;
    if(p->count && (p->records[p->last].state==LB_QUEUED || p->records[p->last].state==LB_DISPATCH_INTENT))return 1;
    if(p->claim_error && !p->claim_partial)return -1;
    assert(p->count<16);p->last=p->count;p->records[p->count++]=*r;p->now+=p->claim_advance;
    return p->claim_error ? -1 : 0;
}
static int save(void *ctx,const LBReceipt *r) {
    Fake *p=ctx;++p->save_calls;assert(lb_receipt_valid(r));unsigned i;
    for(i=0;i<p->count;i++)if(!strcmp(p->records[i].attempt,r->attempt))break;
    assert(i<p->count);int fail=p->save_fail_at==p->save_calls;
    if(!fail || p->save_partial)p->records[i]=*r;
    p->now+=p->save_advance;return fail ? -1 : 0;
}
static int lookup(void *ctx,const char attempt[33],LBReceipt *out) {
    Fake *p=ctx;++p->lookup_calls;if(p->lookup_error)return -1;
    for(unsigned i=0;i<p->count;i++)if(!strcmp(p->records[i].attempt,attempt)){*out=p->records[i];return 0;}
    return 1;
}
static LBLaunchResult launch(void *ctx) {
    Fake *p=ctx;LBReceipt *r=&p->records[p->last];
    assert(r->state==LB_DISPATCH_INTENT && r->dispatch_count==1 && !r->native_confirmed);
    assert(!strcmp(r->title,LB_TITLE));++p->launch_calls;p->now+=p->launch_advance;
    return p->launch_result;
}
static LBAuth auth(void) {
    LBAuth a={.role=LB_ROLE_ADMIN};memcpy(a.resident_build,config.resident_build,65);memcpy(a.instance,config.instance,33);return a;
}
static LBObservation observation(void) {
    LBObservation o={.pid=0x11883,.frame=100,.revision=3,.paused=1};
    memcpy(o.title,LB_TITLE,10);memcpy(o.version,"01.04",6);memcpy(o.build,DEVBUILD,65);memcpy(o.run,INSTANCE,33);return o;
}
static void make_request(unsigned attempt) {
    memset(&request,0,sizeof(request));request.auth=auth();
    snprintf(request.attempt,sizeof(request.attempt),"%032x",attempt);
    memcpy(request.title,LB_TITLE,10);memcpy(request.devloop_build,DEVBUILD,65);request.issued_ms=f.now;request.ttl_ms=1000;
}
static void reset(void) {
    memset(&f,0,sizeof(f));memset(&config,0,sizeof(config));memset(&receipt,0,sizeof(receipt));
    f.now=100;f.launch_result.confirmed=1;f.launch_result.result=0;
    memcpy(config.resident_build,BUILD,65);memcpy(config.instance,INSTANCE,33);config.enabled=1;
    adapter=(LBAdapter){now_ms,recover,claim,save,lookup,launch};
    assert(lb_init(&c,&config,&adapter,&f)==LB_OK);make_request(1);
}
static void queued(void) { int calls=f.launch_calls;assert(lb_offer(&c,&request,&receipt)==LB_ACCEPTED);assert(receipt.state==LB_QUEUED && f.launch_calls==calls); }
static void submitted(void) {
    queued();assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK);
    assert(receipt.state==LB_SUBMITTED && receipt.native_confirmed && receipt.dispatch_count==1 && f.launch_calls==1);
}
static void restart(int same_instance) {
    if(!same_instance)memcpy(config.instance,NEXT_INSTANCE,33);
    assert(lb_init(&c,&config,&adapter,&f)==LB_OK);
    assert(receipt.state!=LB_EMPTY);assert(c.current.state==LB_UNKNOWN && c.current.reason==LB_REASON_RESTART);
}
static void rejected(int expected) { assert(lb_offer(&c,&request,&receipt)==expected);assert(!f.launch_calls && !f.claim_calls); }
static void counted(void) { ++cases; }
int main(void) {
    reset();assert(!f.launch_calls&&!f.claim_calls&&!f.save_calls);counted();
    reset();config.enabled=0;assert(lb_init(&c,&config,&adapter,&f)==LB_OK);rejected(LB_FORBIDDEN);counted();
    reset();queued();assert(lb_receipt_valid(&receipt));LBAuth a=auth();assert(lb_get(&c,&a,request.attempt,&receipt)==LB_OK && receipt.state==LB_QUEUED);counted();
    reset();queued();assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1);counted();
    reset();queued();make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1);counted();
    reset();request.auth.role=LB_ROLE_PHONE;rejected(LB_FORBIDDEN);counted();
    reset();request.auth.role=LB_ROLE_NONE;rejected(LB_FORBIDDEN);counted();
    reset();request.auth.resident_build[0]='f';rejected(LB_STALE);counted();
    reset();request.auth.instance[0]='f';rejected(LB_STALE);counted();
    reset();request.auth.resident_build[64]='x';rejected(LB_BAD_REQUEST);counted();
    reset();memcpy(request.title,"CHRS00012",10);rejected(LB_BAD_REQUEST);counted();
    reset();request.title[9]='x';rejected(LB_BAD_REQUEST);counted();
    reset();request.devloop_build[0]='A';rejected(LB_BAD_REQUEST);counted();
    reset();request.attempt[0]='G';rejected(LB_BAD_REQUEST);counted();
    reset();request.attempt[32]='x';rejected(LB_BAD_REQUEST);counted();
    reset();request.ttl_ms=0;rejected(LB_BAD_REQUEST);counted();
    reset();request.ttl_ms=LB_MAX_TTL_MS+1;rejected(LB_BAD_REQUEST);counted();
    reset();request.issued_ms=UINT64_MAX-1;rejected(LB_BAD_REQUEST);counted();
    reset();request.issued_ms=f.now+1;rejected(LB_STALE);counted();
    reset();request.ttl_ms=LB_MAX_TTL_MS;f.now+=LB_MAX_AGE_MS+1;rejected(LB_STALE);counted();
    reset();f.now+=request.ttl_ms;rejected(LB_STALE);counted();
    reset();request.ttl_ms=LB_MAX_TTL_MS;f.now+=LB_MAX_AGE_MS;queued();counted();
    reset();f.claim_error=1;assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE && c.blocked && !f.launch_calls);a=auth();assert(lb_get(&c,&a,request.attempt,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();f.claim_error=f.claim_partial=1;assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE && f.count==1);restart(0);assert(!f.launch_calls);counted();
    reset();queued();restart(0);assert(!f.launch_calls && lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_CONFLICT);assert(lb_offer(&c,&request,&receipt)==LB_STALE);counted();
    reset();queued();restart(1);assert(!f.launch_calls && lb_offer(&c,&request,&receipt)==LB_CONFLICT);counted();
    reset();queued();f.records[0].state=LB_DISPATCH_INTENT;f.records[0].dispatch_count=1;restart(0);assert(!f.launch_calls);counted();
    reset();submitted();int calls=f.launch_calls;restart(0);assert(f.launch_calls==calls && !c.current.samples);counted();
    reset();queued();f.records[0].format=99;assert(lb_init(&c,&config,&adapter,&f)==LB_UNAVAILABLE && !f.launch_calls);counted();
    reset();f.recover_error=1;assert(lb_init(&c,&config,&adapter,&f)==LB_UNAVAILABLE && !f.launch_calls);counted();
    reset();queued();assert(lb_dispatch_after_response(&c,request.attempt,0,&receipt)==LB_OK && receipt.state==LB_UNKNOWN && !f.launch_calls);assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_CONFLICT);counted();
    reset();queued();assert(lb_dispatch_after_response(&c,request.attempt,0,&receipt)==LB_OK);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && !f.launch_calls);counted();
    reset();queued();assert(lb_dispatch_after_response(&c,request.attempt,0,&receipt)==LB_OK);restart(1);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && !f.launch_calls);counted();
    reset();queued();assert(lb_dispatch_after_response(&c,request.attempt,2,&receipt)==LB_BAD_REQUEST && !f.launch_calls);counted();
    reset();queued();make_request(2);assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_CONFLICT && !f.launch_calls);counted();
    reset();queued();f.now+=1000;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_EXPIRED && !f.launch_calls);counted();
    reset();queued();assert(lb_set_enabled(&c,0)==LB_OK && c.current.state==LB_CANCELLED);assert(lb_set_enabled(&c,1)==LB_OK);assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_CONFLICT && !f.launch_calls);counted();
    reset();queued();f.save_fail_at=1;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE && !f.launch_calls && receipt.state==LB_UNKNOWN);restart(0);assert(!f.launch_calls);counted();
    reset();queued();f.save_fail_at=f.save_partial=1;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE && !f.launch_calls && f.records[0].state==LB_DISPATCH_INTENT);restart(0);assert(!f.launch_calls);counted();
    reset();queued();f.save_advance=1000;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_EXPIRED && receipt.dispatch_count==1 && !f.launch_calls);counted();
    reset();queued();f.now--;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE && !f.launch_calls && receipt.reason==LB_REASON_CLOCK);counted();
    reset();queued();f.launch_result.result=-55;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_NATIVE_REJECTED && f.launch_calls==1);assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_CONFLICT);counted();
    reset();queued();f.launch_result.confirmed=0;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_UNKNOWN && f.launch_calls==1);counted();
    reset();queued();f.launch_result.confirmed=0;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && f.launch_calls==1);counted();
    reset();queued();f.launch_result.confirmed=0;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK);restart(1);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && f.launch_calls==1);counted();
    reset();queued();f.launch_result.confirmed=2;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_UNKNOWN && !receipt.native_confirmed && f.launch_calls==1);counted();
    reset();queued();f.save_fail_at=2;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE && f.launch_calls==1 && f.records[0].state==LB_DISPATCH_INTENT);calls=f.launch_calls;restart(0);assert(f.launch_calls==calls);counted();
    reset();queued();f.save_fail_at=2;f.save_partial=1;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE && f.records[0].state==LB_SUBMITTED);calls=f.launch_calls;restart(0);assert(f.launch_calls==calls);counted();
    reset();queued();f.save_fail_at=2;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_UNAVAILABLE);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE && f.claim_calls==1 && f.launch_calls==1);restart(1);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && f.launch_calls==1);counted();
    reset();f.claim_error=f.claim_partial=1;assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE && f.claim_calls==1 && !f.launch_calls);f.claim_error=0;restart(1);make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1 && !f.launch_calls);counted();
    reset();queued();f.launch_result.confirmed=0;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK);restart(0);make_request(1);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.claim_calls==1);make_request(2);queued();f.launch_result.confirmed=1;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_SUBMITTED && f.launch_calls==2 && f.count==2 && f.records[0].state==LB_UNKNOWN);counted();
    reset();queued();f.launch_advance=1000000;assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && receipt.state==LB_SUBMITTED && f.now>receipt.expires_ms);counted();
    reset();submitted();char first[33];memcpy(first,request.attempt,33);make_request(2);queued();assert(lb_dispatch_after_response(&c,request.attempt,1,&receipt)==LB_OK && f.launch_calls==2);make_request(1);assert(lb_offer(&c,&request,&receipt)==LB_CONFLICT && f.launch_calls==2);a=auth();assert(lb_get(&c,&a,first,&receipt)==LB_OK && receipt.state==LB_SUBMITTED);counted();
    reset();a=auth();assert(lb_get(&c,&a,request.attempt,&receipt)==LB_NOT_FOUND);a.role=LB_ROLE_PHONE;assert(lb_get(&c,&a,request.attempt,&receipt)==LB_FORBIDDEN);counted();
    reset();submitted();LBObservation o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.samples==1);o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_OBSERVED && receipt.samples==2 && f.launch_calls==1);assert(lb_receipt_valid(&receipt));counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_STALE && c.current.samples==1);counted();
    reset();submitted();o=observation();o.build[0]='0';a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.pid++;o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.run[0]='f';o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.revision++;o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.frame--;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();o.paused=0;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();o.faulted=1;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK && receipt.state==LB_UNKNOWN);counted();
    reset();submitted();o=observation();a=auth();o.frame=0;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_BAD_REQUEST && !c.current.samples);counted();
    reset();submitted();o=observation();a=auth();a.role=LB_ROLE_PHONE;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_FORBIDDEN && !c.current.samples);counted();
    reset();submitted();o=observation();a=auth();f.save_fail_at=f.save_calls+1;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_UNAVAILABLE && receipt.state==LB_UNKNOWN && !receipt.samples);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);calls=f.launch_calls;restart(0);assert(f.launch_calls==calls && !c.current.samples);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);char observed[33];memcpy(observed,request.attempt,33);f.now--;make_request(2);assert(lb_offer(&c,&request,&receipt)==LB_UNAVAILABLE && f.launch_calls==1 && f.claim_calls==1);assert(lb_get(&c,&a,observed,&receipt)==LB_OK && receipt.state==LB_UNKNOWN && receipt.reason==LB_REASON_CLOCK && !receipt.samples);counted();
    reset();submitted();o=observation();a=auth();assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);o.frame++;assert(lb_observe(&c,&a,request.attempt,&o,&receipt)==LB_OK);memcpy(observed,request.attempt,33);make_request(2);queued();restart(0);make_request(3);queued();a=auth();assert(lb_get(&c,&a,observed,&receipt)==LB_OK && receipt.state==LB_OBSERVED && !strcmp(receipt.instance,INSTANCE) && strcmp(receipt.instance,a.instance) && c.current.state==LB_QUEUED && strcmp(c.current.attempt,observed) && f.launch_calls==1);counted();
    reset();config.instance[0]='Z';assert(lb_init(&c,&config,&adapter,&f)==LB_BAD_REQUEST && !f.launch_calls);counted();
    reset();adapter.launch_fixed_title=0;assert(lb_init(&c,&config,&adapter,&f)==LB_BAD_REQUEST && !f.launch_calls);counted();
    reset();assert(lb_set_enabled(&c,2)==LB_BAD_REQUEST);assert(!strcmp(lb_state_name(LB_OBSERVED),"observed_script_only"));counted();
    printf("PASS portable launch broker actual-core tests: %u cases\n",cases);return 0;
}
