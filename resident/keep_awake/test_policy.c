#include "policy.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static const char *instance="11111111111111111111111111111111";
static RKARequest request(RKAState *state,uint32_t ttl,uint32_t duration) {
    RKARequest command={0};command.revision=state->revision;command.ttl_ms=ttl;command.max_duration_ms=duration;
    memcpy(command.instance_id,instance,33);memset(command.lease_id,'2',32);memset(command.job_id,'3',32);
    return command;
}
static void initialized(RKAState *state,uint64_t now) { rka_policy_init(state,instance);rka_policy_step(state,now,1); }
static void wire_value(unsigned char *wire,unsigned offset,uint32_t value) {
    for(unsigned i=0;i<4;i++) wire[offset+i]=(unsigned char)(value>>(i*8));
}
int main(void) {
    RKAState state;initialized(&state,10000);assert(!state.active);assert(!rka_policy_step(&state,11000,1));
    assert(!state.tick_count&&state.revision==0);
    RKARequest command=request(&state,5000,30000);
    assert(rka_policy_apply(&state,&command,11000)==200);assert(state.active&&state.revision==1&&state.expires_ms==16000);
    assert(rka_policy_step(&state,11000,1));rka_policy_tick(&state,11000,0);assert(state.tick_count==1);
    assert(!rka_policy_step(&state,11999,1));assert(rka_policy_step(&state,12000,1));rka_policy_tick(&state,12000,0);
    assert(rka_policy_apply(&state,&command,12000)==409); /* stale CAS */
    command=request(&state,30000,0);command.job_id[0]='4';assert(rka_policy_apply(&state,&command,12000)==409);
    command=request(&state,30000,1);assert(rka_policy_apply(&state,&command,12000)==400);
    command=request(&state,30000,0);assert(rka_policy_apply(&state,&command,12000)==200);
    assert(state.session_expires_ms==41000&&state.expires_ms==41000); /* absolute ceiling */
    for(uint64_t now=16000;now<=40000;now+=4000) rka_policy_step(&state,now,1);
    rka_policy_step(&state,41000,1);assert(!state.active&&!strcmp(state.reason,"session_expired")&&state.revision==3);
    command=request(&state,30000,0);assert(rka_policy_apply(&state,&command,41000)==400);
    command=request(&state,4999,30000);assert(rka_policy_apply(&state,&command,41000)==400);
    command=request(&state,30001,30000);assert(rka_policy_apply(&state,&command,41000)==400);
    command=request(&state,5000,29999);assert(rka_policy_apply(&state,&command,41000)==400);
    command=request(&state,5000,1800001);assert(rka_policy_apply(&state,&command,41000)==400);
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,41000)==200);
    assert(rka_policy_step(&state,41000,1));rka_policy_tick(&state,41000,0);
    rka_policy_step(&state,45000,1);rka_policy_step(&state,46000,1);
    assert(!state.active&&!strcmp(state.reason,"lease_expired"));
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,46000)==200);
    rka_policy_step(&state,46001,0);assert(!state.active&&!strcmp(state.reason,"network_lost"));
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,46001)==503);
    rka_policy_step(&state,46002,1);command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,46002)==200);
    rka_policy_step(&state,52003,1);assert(!state.active&&!strcmp(state.reason,"worker_gap"));
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,52003)==200);
    rka_policy_tick(&state,52003,0);rka_policy_step(&state,50000,1);
    assert(!state.active&&!strcmp(state.reason,"clock_regression")&&state.last_tick_ms<=50000);
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,50000)==200);
    rka_policy_tick(&state,50000,-7);assert(!state.active&&!strcmp(state.reason,"tick_failed"));
    command=request(&state,5000,30000);assert(rka_policy_apply(&state,&command,50000)==200);
    command=request(&state,0,0);assert(rka_policy_apply(&state,&command,50000)==200);
    assert(!state.active&&!strcmp(state.reason,"released"));assert(rka_policy_apply(&state,&command,50000)==409);
    unsigned char wire[128]={0};wire_value(wire,0,RKA_MAGIC);wire_value(wire,4,1);wire_value(wire,12,5000);wire_value(wire,16,30000);
    memset(wire+32,'1',32);memset(wire+64,'2',32);memset(wire+96,'3',32);
    assert(rka_decode(&command,wire,sizeof(wire)));assert(command.ttl_ms==5000);
    wire[20]=1;assert(!rka_decode(&command,wire,sizeof(wire)));wire[20]=0;
    wire[64]='A';assert(!rka_decode(&command,wire,sizeof(wire)));wire[64]='2';
    assert(!rka_decode(&command,wire,127));
    initialized(&state,UINT64_MAX-100);command=request(&state,5000,30000);
    assert(rka_policy_apply(&state,&command,UINT64_MAX-100)==503&&!state.active);
    initialized(&state,10000);state.revision=UINT32_MAX;command=request(&state,5000,30000);
    assert(rka_policy_apply(&state,&command,10000)==503&&!state.active);
    initialized(&state,10000);command=request(&state,5000,30000);
    assert(rka_policy_apply(&state,&command,10000)==200);
    rka_policy_step(&state,14999,1);command=request(&state,5000,0);
    assert(rka_policy_apply(&state,&command,15000)==409&&!state.active);
    assert(!strcmp(state.reason,"lease_expired")&&state.revision==2);
    puts("Resident keep-awake policy: PASS");return 0;
}
