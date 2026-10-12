/* Qualification candidate. Native submission stays disabled in every build. */
#include "service.h"
#include "store.h"
#include "native.h"
#include "../platform.h"

static LBCore core;
static LBStore store;
static int ready;

void rlb_init(void) {
    LBConfig config={0};
    ready=0;
    if(R_STRLEN(R_BUILD_ID)!=64) { r_log("launch broker build identity unavailable",-1);return; }
    R_MEMCPY(config.resident_build,R_BUILD_ID,65);
    if(!lb_native_instance(config.instance)) {
        r_log("launch broker identity unavailable; inspection retained",-1);
        return;
    }
    if(lb_store_init(&store)<0) {
        r_log("launch broker storage unavailable; inspection retained",-1);
        return;
    }
    config.enabled=0;
#if defined(LB_HOST_SERVICE_TEST_ENABLED) && !defined(__vita__)
    /* POSIX transport fixture only; this branch cannot enter a Vita module. */
    config.enabled=r_pair_exists("ux0:data/vita-resident/fixture-enable-launch")==1;
#endif
    LBAdapter adapter={lb_native_now,lb_store_recover_last,lb_store_claim,
                       lb_store_save,lb_store_lookup,lb_native_launch};
    int result=lb_init(&core,&config,&adapter,&store);
    ready=core.initialized;
    r_log("launch broker qualification only",result);
}

int rlb_request(int admin,const char *method,const char *path,const void *body,
                size_t size,char *reply,size_t capacity,LBDeferred *deferred) {
    if(deferred)R_MEMSET(deferred,0,sizeof(*deferred));
    if(admin!=1) {
        R_SNPRINTF(reply,capacity,"{\"error\":\"Desktop administrator required\"}");
        return 403;
    }
    if(!R_STRCMP(path,"/devloop-launch/inventory")) {
        if(R_STRCMP(method,"GET")||size) {
            R_SNPRINTF(reply,capacity,"{\"error\":\"Body-free inventory GET required\"}");
            return 400;
        }
        if(lb_native_inventory(reply,capacity)<0) {
            R_SNPRINTF(reply,capacity,"{\"error\":\"Native app inventory unavailable\"}");
            return 503;
        }
        return 200;
    }
    if(!ready) {
        R_SNPRINTF(reply,capacity,"{\"error\":\"Launch broker unavailable; ordinary Resident inspection retained\"}");
        return 503;
    }
    return lb_http_dispatch(&core,admin,method,path,body,size,reply,capacity,deferred);
}

void rlb_after_response(const LBDeferred *deferred,int complete) {
    if(!ready||!deferred||!deferred->armed)return;
    LBReceipt out={0};
    int result=lb_dispatch_after_response(&core,deferred->attempt,complete,&out);
    r_log("launch broker deferred result",result);
}
