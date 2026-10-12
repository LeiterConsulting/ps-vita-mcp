#include "launch_broker.h"
#include <stddef.h>
#include <string.h>

static int hex(const char *value,unsigned length) {
    for(unsigned i=0;i<length;i++) if(!((value[i]>='0'&&value[i]<='9')||(value[i]>='a'&&value[i]<='f'))) return 0;
    return value[length]==0;
}
static int literal(const char *value,const char *expected,unsigned length) {
    return memcmp(value,expected,length)==0 && value[length]==0;
}
static int operational(const LBCore *c) { return c && c->initialized && !c->blocked; }
static int authorization(const LBCore *c,const LBAuth *auth) {
    if(!operational(c)) return LB_UNAVAILABLE;
    if(!auth || auth->role!=LB_ROLE_ADMIN) return LB_FORBIDDEN;
    if(!hex(auth->resident_build,64)||!hex(auth->instance,32)) return LB_BAD_REQUEST;
    return strcmp(auth->resident_build,c->config.resident_build)||strcmp(auth->instance,c->config.instance) ? LB_STALE : LB_OK;
}
static void output(const LBCore *c,LBReceipt *out) { if(out && c->has_current) *out=c->current; }
static int clock_now(LBCore *c,uint64_t *now) {
    *now=c->adapter.now_ms(c->ctx);
    if(*now<c->last_ms) {
        c->blocked=1;
        if(c->has_current) {
            c->current.state=LB_UNKNOWN;c->current.reason=LB_REASON_CLOCK;c->current.samples=0;
            /* Best effort only; a clock fault never permits dispatch or replay. */
            c->adapter.save(c->ctx,&c->current);
        }
        return 0;
    }
    c->last_ms=*now;return 1;
}
static int pending(LBState state) { return state==LB_QUEUED || state==LB_DISPATCH_INTENT; }
static int persist(LBCore *c) {
    if(c->adapter.save(c->ctx,&c->current)==0) return LB_OK;
    c->current.state=LB_UNKNOWN;c->current.reason=LB_REASON_STORAGE;c->current.samples=0;
    c->blocked=1;return LB_UNAVAILABLE;
}
static int finish(LBCore *c,LBState state,LBReason reason,LBReceipt *out) {
    c->current.state=state;c->current.reason=reason;
    if(state!=LB_OBSERVED)c->current.samples=0;
    int result=persist(c);output(c,out);return result;
}
static int observation_valid(const LBObservation *o) {
    return o && literal(o->title,LB_TITLE,9) && literal(o->version,"01.04",5) &&
        hex(o->build,64) && hex(o->run,32) && o->pid>0 && o->frame>0 && o->revision>0 &&
        (o->paused==0||o->paused==1) && (o->faulted==0||o->faulted==1);
}
int lb_receipt_valid(const LBReceipt *r) {
    if(!r || r->format!=LB_FORMAT || r->state<LB_QUEUED || r->state>LB_CANCELLED ||
       (unsigned)r->reason>LB_REASON_OBSERVATION || !hex(r->attempt,32) ||
       !literal(r->title,LB_TITLE,9) || !hex(r->resident_build,64) || !hex(r->instance,32) ||
       !hex(r->devloop_build,64) || r->expires_ms<=r->issued_ms ||
       r->expires_ms-r->issued_ms>LB_MAX_TTL_MS || r->accepted_ms<r->issued_ms ||
       r->accepted_ms>=r->expires_ms || r->dispatch_count>1 ||
       (r->native_confirmed!=0 && r->native_confirmed!=1) || r->samples>2) return 0;
    if(r->state==LB_QUEUED && (r->dispatch_count || r->native_confirmed || r->samples)) return 0;
    if((r->state==LB_DISPATCH_INTENT || r->state==LB_SUBMITTED || r->state==LB_NATIVE_REJECTED || r->state==LB_OBSERVED) && r->dispatch_count!=1) return 0;
    if(r->state==LB_SUBMITTED || r->state==LB_OBSERVED) {
        if(!r->native_confirmed || r->native_result<0) return 0;
    }
    if(r->state==LB_NATIVE_REJECTED && (!r->native_confirmed || r->native_result>=0)) return 0;
    if(r->samples && (!observation_valid(&r->observation) || strcmp(r->observation.build,r->devloop_build) || !r->observation.paused || r->observation.faulted)) return 0;
    if(r->state==LB_OBSERVED && r->samples!=2) return 0;
    if(r->state!=LB_SUBMITTED && r->state!=LB_OBSERVED && r->samples) return 0;
    return 1;
}
int lb_init(LBCore *c,const LBConfig *config,const LBAdapter *adapter,void *ctx) {
    if(!c || !config || !adapter || !hex(config->resident_build,64)||!hex(config->instance,32) ||
       (config->enabled!=0 && config->enabled!=1) || !adapter->now_ms || !adapter->recover_last ||
       !adapter->claim || !adapter->save || !adapter->lookup || !adapter->launch_fixed_title) return LB_BAD_REQUEST;
    memset(c,0,sizeof(*c));c->config=*config;c->adapter=*adapter;c->ctx=ctx;c->initialized=1;
    c->last_ms=adapter->now_ms(ctx);
    LBReceipt recovered={0};int result=adapter->recover_last(ctx,&recovered);
    if(result==0) return LB_OK;
    if(result!=1 || !lb_receipt_valid(&recovered) || strcmp(recovered.resident_build,config->resident_build)) { c->blocked=1;return LB_UNAVAILABLE; }
    /* Even same-instance service reconstruction is never a dispatch-resume signal. */
    c->current=recovered;c->has_current=1;
    return finish(c,LB_UNKNOWN,LB_REASON_RESTART,0);
}
int lb_offer(LBCore *c,const LBRequest *request,LBReceipt *out) {
    if(!request) return LB_BAD_REQUEST;
    int result=authorization(c,&request->auth);if(result!=LB_OK)return result;
    if(!c->config.enabled)return LB_FORBIDDEN;
    if(!hex(request->attempt,32)||!hex(request->devloop_build,64)||!literal(request->title,LB_TITLE,9) ||
       !request->ttl_ms || request->ttl_ms>LB_MAX_TTL_MS || request->issued_ms>UINT64_MAX-request->ttl_ms) return LB_BAD_REQUEST;
    if(c->has_current && (pending(c->current.state)||!strcmp(c->current.attempt,request->attempt) ||
       (c->current.state==LB_UNKNOWN && !strcmp(c->current.instance,c->config.instance)))) return LB_CONFLICT;
    uint64_t now;if(!clock_now(c,&now))return LB_UNAVAILABLE;
    uint64_t expires=request->issued_ms+request->ttl_ms;
    if(now<request->issued_ms || now-request->issued_ms>LB_MAX_AGE_MS || now>=expires)return LB_STALE;
    LBReceipt receipt={0};receipt.format=LB_FORMAT;receipt.state=LB_QUEUED;
    memcpy(receipt.attempt,request->attempt,sizeof(receipt.attempt));memcpy(receipt.title,request->title,sizeof(receipt.title));
    memcpy(receipt.resident_build,request->auth.resident_build,sizeof(receipt.resident_build));
    memcpy(receipt.instance,request->auth.instance,sizeof(receipt.instance));
    memcpy(receipt.devloop_build,request->devloop_build,sizeof(receipt.devloop_build));
    receipt.issued_ms=request->issued_ms;receipt.expires_ms=expires;receipt.accepted_ms=now;receipt.native_result=-1;
    result=c->adapter.claim(c->ctx,&receipt);
    if(result==1)return LB_CONFLICT;
    c->current=receipt;c->has_current=1;
    if(result!=0) { c->current.state=LB_UNKNOWN;c->current.reason=LB_REASON_STORAGE;c->blocked=1;output(c,out);return LB_UNAVAILABLE; }
    output(c,out);return LB_ACCEPTED;
}
int lb_dispatch_after_response(LBCore *c,const char attempt[33],int response_complete,LBReceipt *out) {
    if(!operational(c))return LB_UNAVAILABLE;
    if(!attempt || !hex(attempt,32)||(response_complete!=0&&response_complete!=1))return LB_BAD_REQUEST;
    if(!c->has_current || strcmp(c->current.attempt,attempt)||c->current.state!=LB_QUEUED)return LB_CONFLICT;
    if(strcmp(c->current.instance,c->config.instance))return LB_STALE;
    if(!response_complete)return finish(c,LB_UNKNOWN,LB_REASON_RESPONSE,out);
    if(!c->config.enabled)return finish(c,LB_CANCELLED,LB_REASON_DISABLED,out);
    uint64_t now;
    if(!clock_now(c,&now)) { c->current.state=LB_UNKNOWN;c->current.reason=LB_REASON_CLOCK;output(c,out);return LB_UNAVAILABLE; }
    if(now>=c->current.expires_ms)return finish(c,LB_EXPIRED,LB_REASON_EXPIRY,out);
    c->current.state=LB_DISPATCH_INTENT;c->current.dispatch_count=1;c->current.dispatch_ms=now;
    int result=persist(c);if(result!=LB_OK) { output(c,out);return result; }
    /* Sync may take time. Recheck before the irreversible native submission. */
    if(!clock_now(c,&now)) { c->current.state=LB_UNKNOWN;c->current.reason=LB_REASON_CLOCK;output(c,out);return LB_UNAVAILABLE; }
    if(now>=c->current.expires_ms)return finish(c,LB_EXPIRED,LB_REASON_EXPIRY,out);
    LBLaunchResult native=c->adapter.launch_fixed_title(c->ctx);
    c->current.native_result=native.result;c->current.native_confirmed=native.confirmed==1;
    if(native.confirmed!=1)return finish(c,LB_UNKNOWN,LB_REASON_NATIVE,out);
    /* An expiry during a blocking launch never becomes a cancellation claim. */
    return finish(c,native.result<0?LB_NATIVE_REJECTED:LB_SUBMITTED,LB_REASON_NONE,out);
}
int lb_get(LBCore *c,const LBAuth *auth,const char attempt[33],LBReceipt *out) {
    /* A storage-blocked service can still disclose its cached uncertain receipt. */
    if(!c || !c->initialized)return LB_UNAVAILABLE;
    if(!auth || auth->role!=LB_ROLE_ADMIN)return LB_FORBIDDEN;
    if(!hex(auth->resident_build,64)||!hex(auth->instance,32)||!attempt||!hex(attempt,32))return LB_BAD_REQUEST;
    if(strcmp(auth->resident_build,c->config.resident_build)||strcmp(auth->instance,c->config.instance))return LB_STALE;
    if(c->has_current && !strcmp(c->current.attempt,attempt)) { if(out)*out=c->current;return LB_OK; }
    if(c->blocked)return LB_UNAVAILABLE;
    LBReceipt receipt={0};int result=c->adapter.lookup(c->ctx,attempt,&receipt);
    if(result==1)return LB_NOT_FOUND;
    if(result!=0||!lb_receipt_valid(&receipt)||strcmp(receipt.attempt,attempt))return LB_UNAVAILABLE;
    if(out)*out=receipt;
    return LB_OK;
}
int lb_observe(LBCore *c,const LBAuth *auth,const char attempt[33],const LBObservation *o,LBReceipt *out) {
    int result=authorization(c,auth);if(result!=LB_OK)return result;
    if(!attempt||!hex(attempt,32)||!observation_valid(o))return LB_BAD_REQUEST;
    if(!c->has_current || strcmp(c->current.attempt,attempt)||c->current.state!=LB_SUBMITTED)return LB_CONFLICT;
    if(strcmp(c->current.instance,c->config.instance))return LB_STALE;
    if(strcmp(o->build,c->current.devloop_build)||!o->paused||o->faulted)
        return finish(c,LB_UNKNOWN,LB_REASON_OBSERVATION,out);
    if(c->current.samples) {
        LBObservation *old=&c->current.observation;
        if(old->pid!=o->pid || strcmp(old->run,o->run) || old->revision!=o->revision || o->frame<old->frame)
            return finish(c,LB_UNKNOWN,LB_REASON_OBSERVATION,out);
        if(o->frame==old->frame)return LB_STALE;
    }
    c->current.observation=*o;c->current.samples++;
    if(c->current.samples==2) { c->current.state=LB_OBSERVED;c->current.reason=LB_REASON_NONE; }
    result=persist(c);output(c,out);return result;
}
int lb_set_enabled(LBCore *c,int enabled) {
    if(!operational(c))return LB_UNAVAILABLE;
    if(enabled!=0&&enabled!=1)return LB_BAD_REQUEST;
    c->config.enabled=enabled;
    if(!enabled && c->has_current && c->current.state==LB_QUEUED)return finish(c,LB_CANCELLED,LB_REASON_DISABLED,0);
    return LB_OK;
}
int lb_status_clock(LBCore *c,uint64_t *now_ms) {
    if(!c||!c->initialized||!now_ms)return LB_UNAVAILABLE;
    return clock_now(c,now_ms)?LB_OK:LB_UNAVAILABLE;
}
const char *lb_state_name(LBState state) {
    static const char *const names[]={"empty","queued","dispatch_intent","submitted","native_rejected","unknown","observed_script_only","expired_before_submission","cancelled_before_submission"};
    return (unsigned)state<=LB_CANCELLED ? names[state] : "invalid";
}
