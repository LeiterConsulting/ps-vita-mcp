#include "policy.h"
#include "../platform.h"
#include <limits.h>
static int hex_id(const char *id) {
    for(unsigned i=0;i<32;i++) if(!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f'))) return 0;
    return 1;
}
static int same_id(const char *left,const char *right) {
    unsigned difference=0;
    for(unsigned i=0;i<32;i++) difference|=(unsigned char)left[i]^(unsigned char)right[i];
    return difference==0;
}
static uint32_t little(const unsigned char *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
void rka_policy_init(RKAState *state,const char instance_id[33]) {
    R_MEMSET(state,0,sizeof(*state));
    R_MEMCPY(state->instance_id,instance_id,33);
    state->reason="inactive";
}
int rka_decode(RKARequest *request,const unsigned char *wire,size_t size) {
    if(size!=RKA_WIRE_BYTES||little(wire)!=RKA_MAGIC||little(wire+4)!=RKA_PROTOCOL||
       little(wire+20)||little(wire+24)||little(wire+28)) return 0;
    R_MEMSET(request,0,sizeof(*request));
    request->revision=little(wire+8);request->ttl_ms=little(wire+12);request->max_duration_ms=little(wire+16);
    R_MEMCPY(request->instance_id,wire+32,32);R_MEMCPY(request->lease_id,wire+64,32);R_MEMCPY(request->job_id,wire+96,32);
    return hex_id(request->instance_id)&&hex_id(request->lease_id)&&hex_id(request->job_id);
}
void rka_policy_end(RKAState *state,const char *reason) {
    if(state->active&&state->revision<UINT32_MAX) state->revision++;
    state->active=0;state->expires_ms=0;state->session_expires_ms=0;
    R_MEMSET(state->lease_id,0,sizeof(state->lease_id));R_MEMSET(state->job_id,0,sizeof(state->job_id));
    state->reason=reason;
}
int rka_policy_step(RKAState *state,uint64_t now_ms,int network_ready) {
    if(state->clock_valid) {
        if(now_ms<state->last_clock_ms) { rka_policy_end(state,"clock_regression");state->last_tick_ms=0; }
        else if(now_ms-state->last_clock_ms>RKA_GAP_MAX) rka_policy_end(state,"worker_gap");
    }
    state->clock_valid=1;state->last_clock_ms=now_ms;state->network_ready=network_ready!=0;
    if(state->active&&!network_ready) rka_policy_end(state,"network_lost");
    if(state->active&&now_ms>=state->session_expires_ms) rka_policy_end(state,"session_expired");
    if(state->active&&now_ms>=state->expires_ms) rka_policy_end(state,"lease_expired");
    return state->active&&(state->tick_pending||!state->tick_count||now_ms-state->last_tick_ms>=1000);
}
int rka_policy_apply(RKAState *state,const RKARequest *request,uint64_t now_ms) {
    /* A request sampled at the deadline must not revive an expired owner. */
    rka_policy_step(state,now_ms,state->network_ready);
    if(!hex_id(request->instance_id)||!hex_id(request->lease_id)||!hex_id(request->job_id)) return 400;
    if(request->ttl_ms&&(request->ttl_ms<RKA_TTL_MIN||request->ttl_ms>RKA_TTL_MAX)) return 400;
    if(!same_id(state->instance_id,request->instance_id)||request->revision!=state->revision) return 409;
    if(state->revision==UINT32_MAX||!state->clock_valid||!state->network_ready) return 503;
    if(state->active) {
        if(!same_id(state->lease_id,request->lease_id)||!same_id(state->job_id,request->job_id)) return 409;
        if(request->max_duration_ms) return 400;
        if(!request->ttl_ms) { rka_policy_end(state,"released");return 200; }
    } else {
        if(!request->ttl_ms) return 409;
        if(request->max_duration_ms<RKA_SESSION_MIN||request->max_duration_ms>RKA_SESSION_MAX) return 400;
        if(UINT64_MAX-now_ms<request->max_duration_ms) return 503;
        state->session_expires_ms=now_ms+request->max_duration_ms;
        state->tick_pending=1;
        R_MEMCPY(state->lease_id,request->lease_id,33);R_MEMCPY(state->job_id,request->job_id,33);
    }
    if(UINT64_MAX-now_ms<request->ttl_ms) { rka_policy_end(state,"clock_overflow");return 503; }
    state->expires_ms=now_ms+request->ttl_ms;
    if(state->expires_ms>state->session_expires_ms) state->expires_ms=state->session_expires_ms;
    state->active=1;state->revision++;state->reason="working";
    return 200;
}
void rka_policy_tick(RKAState *state,uint64_t now_ms,int result) {
    if(!state->active) return;
    state->last_tick_ms=now_ms;state->tick_count++;state->tick_result=result;state->tick_pending=0;
    if(result<0) rka_policy_end(state,"tick_failed");
}
