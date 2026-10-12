/* Test-only DLL boundary: real portable core, simulated persistent/native IO.
   Never linked into Resident or a Vita package. Serialized by the HTTP fixture. */
#include "../resident/launch_broker/launch_broker.h"
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif
static LBCore core;
static LBReceipt records[64];
static unsigned count,launches;
static uint64_t clock_ms;
static int fault;
static char text[2048];
static uint64_t now(void *ctx) {(void)ctx;return ++clock_ms;}
static int recover(void *ctx,LBReceipt *out) {(void)ctx;if(!count)return 0;*out=records[count-1];return 1;}
static int claim(void *ctx,const LBReceipt *in) {
    (void)ctx;if(fault==1)return -1;
    for(unsigned i=0;i<count;i++)if(!strcmp(records[i].attempt,in->attempt))return 1;
    if(count>=64)return -1;
    records[count++]=*in;return 0;
}
static int save(void *ctx,const LBReceipt *in) {
    (void)ctx;if(fault==2)return -1;
    for(unsigned i=0;i<count;i++)if(!strcmp(records[i].attempt,in->attempt)){records[i]=*in;return 0;}
    return -1;
}
static int lookup(void *ctx,const char attempt[33],LBReceipt *out) {
    (void)ctx;for(unsigned i=0;i<count;i++)if(!strcmp(records[i].attempt,attempt)){*out=records[i];return 0;}return 1;
}
static LBLaunchResult launch(void *ctx) {
    (void)ctx;launches++;LBLaunchResult r={fault!=4,fault==3?-1:0};return r;
}
static const char *result(int code,const LBReceipt *r) {
    if((code==LB_OK||code==LB_ACCEPTED)&&r&&lb_receipt_valid(r)) {
        snprintf(text,sizeof(text),"{\"code\":%d,\"attempt\":\"%s\",\"title_id\":\"%s\",\"expected_devloop_build\":\"%s\",\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"state\":\"%s\",\"dispatch_count\":%u,\"native_confirmed\":%d,\"native_result\":%d}",code,r->attempt,r->title,r->devloop_build,r->resident_build,r->instance,lb_state_name(r->state),r->dispatch_count,r->native_confirmed,r->native_result);
    } else snprintf(text,sizeof(text),"{\"code\":%d,\"error\":\"broker refused\"}",code);
    return text;
}
EXPORT int lb_host_init(int restart) {
    if(!restart){count=launches=0;clock_ms=1000;fault=0;memset(records,0,sizeof(records));}
    LBConfig config={0};memset(config.resident_build,'a',64);memset(config.instance,restart?'c':'b',32);config.enabled=1;
    LBAdapter adapter={now,recover,claim,save,lookup,launch};return lb_init(&core,&config,&adapter,0);
}
EXPORT const char *lb_host_status(void) {
    snprintf(text,sizeof(text),"{\"app\":\"Vita Resident Launch Broker\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"enabled\":%s,\"now_ms\":%llu}",core.config.resident_build,core.config.instance,core.config.enabled?"true":"false",(unsigned long long)now(0));return text;
}
static LBAuth auth(int role,const char *build,const char *instance) {
    LBAuth a={0};a.role=(LBRole)role;snprintf(a.resident_build,sizeof(a.resident_build),"%s",build);snprintf(a.instance,sizeof(a.instance),"%s",instance);return a;
}
EXPORT const char *lb_host_offer(int role,const char *build,const char *instance,const char *attempt,const char *title,const char *devbuild,uint64_t issued,uint32_t ttl) {
    LBRequest q={0};LBReceipt out={0};q.auth=auth(role,build,instance);
    snprintf(q.attempt,sizeof(q.attempt),"%s",attempt);snprintf(q.title,sizeof(q.title),"%s",title);snprintf(q.devloop_build,sizeof(q.devloop_build),"%s",devbuild);q.issued_ms=issued;q.ttl_ms=ttl;
    int code=lb_offer(&core,&q,&out);return result(code,&out);
}
EXPORT const char *lb_host_get(int role,const char *build,const char *instance,const char *attempt) {
    LBAuth a=auth(role,build,instance);LBReceipt out={0};int code=lb_get(&core,&a,attempt,&out);return result(code,&out);
}
EXPORT const char *lb_host_dispatch(const char *attempt,int complete) {
    LBReceipt out={0};int code=lb_dispatch_after_response(&core,attempt,complete,&out);return result(code,&out);
}
EXPORT unsigned lb_host_launches(void) {return launches;}
EXPORT void lb_host_fault(int value) {fault=value;}
EXPORT int lb_host_enabled(int value) {return lb_set_enabled(&core,value);}
