#include "native.h"
#include "../platform.h"
#ifdef LB_NATIVE_HOST
#include "test_native_platform.h"
#else
#include <psp2/appmgr.h>
#endif

/* Retained for the complete native module lifetime, independent of service
   reconnects or core reconstruction. Failed/partial RNG is never retried. */
static int identity_state;
static char identity[33];

int lb_native_instance(char out[33]) {
    if(!out) return 0;
    out[0]=0;
    int state=__atomic_load_n(&identity_state,__ATOMIC_ACQUIRE);
    if(state==2) { R_MEMCPY(out,identity,sizeof(identity));return 1; }
    int expected=0;
    if(!__atomic_compare_exchange_n(&identity_state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
        return 0;
    unsigned char bytes[16]={0};unsigned nonzero=0;
    if(r_pair_random(bytes,sizeof(bytes))!=0) {
        __atomic_store_n(&identity_state,-1,__ATOMIC_RELEASE);return 0;
    }
    for(unsigned i=0;i<sizeof(bytes);i++) nonzero|=bytes[i];
    if(!nonzero) { __atomic_store_n(&identity_state,-1,__ATOMIC_RELEASE);return 0; }
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<sizeof(bytes);i++) {
        identity[2*i]=hex[bytes[i]>>4];identity[2*i+1]=hex[bytes[i]&15u];
    }
    identity[32]=0;
    __atomic_store_n(&identity_state,2,__ATOMIC_RELEASE);
    R_MEMCPY(out,identity,sizeof(identity));return 1;
}

uint64_t lb_native_now(void *ctx) { (void)ctx;return r_pair_mono(); }

LBLaunchResult lb_native_launch(void *ctx) {
    (void)ctx;
    /* The locked SDK's _sceAppMgrGetAppState describes the calling app's
       pending events/overlay, not the displayed PID. Neither that structure,
       running-app enumeration nor a PC claim proves safe foreground state.
       Do not link sceAppMgrLaunchAppByUri/Name until an authoritative native
       guard and protected-UI policy have separate implementation/proof. */
    LBLaunchResult refused={0,LB_NATIVE_LAUNCH_UNQUALIFIED};return refused;
}

static int title_valid(const char title[32]) {
    for(unsigned i=0;i<9;i++)
        if(!((title[i]>='A'&&title[i]<='Z')||(title[i]>='0'&&title[i]<='9'))) return 0;
    return title[9]==0;
}

int lb_native_inventory(char *reply,size_t capacity) {
    if(!reply||!capacity) return -1;
    reply[0]=0;
    SceInt32 apps[16]={0};
    int status=sceAppMgrGetRunningAppIdListForShell(apps,16);
    char json[LB_NATIVE_INVENTORY_CAPACITY];
    int count=R_SNPRINTF(json,sizeof(json),
        "{\"app\":\"Vita Resident Launch Inventory\",\"protocol\":1,\"sampled_ms\":%llu,"
        "\"available\":%s,\"enumeration_result\":%d,\"capacity\":16,"
        "\"snapshot_atomic\":false,\"foreground_verified\":false,"
        "\"protected_ui_verified\":false,\"native_submission_enabled\":false,\"entries\":[",
        (unsigned long long)lb_native_now(0),status>=0?"true":"false",status);
    if(count<0||(size_t)count>=sizeof(json)) return -1;
    size_t used=(size_t)count;unsigned entries=0;
    /* Historical calls can return success 0 while filling later slots. Scan
       every initialized slot; neither returned count nor ordering is focus. */
    if(status>=0) for(unsigned i=0;i<16;i++) {
        if(apps[i]<=0) continue;
        int duplicate=0;
        for(unsigned earlier=0;earlier<i;earlier++) if(apps[earlier]==apps[i]) duplicate=1;
        if(duplicate) continue;
        SceUID pid=sceAppMgrGetProcessIdByAppIdForShell(apps[i]);
        char title[32]={0};int resolved=0;
        if(pid>0 && sceAppMgrGetNameById(pid,title)>=0 && title_valid(title)) resolved=1;
        if(resolved) count=R_SNPRINTF(json+used,sizeof(json)-used,
            "%s{\"app_id\":%d,\"pid\":%d,\"title_id\":\"%s\",\"resolved\":true}",
            entries?",":"",(int)apps[i],(int)pid,title);
        else if(pid>0) count=R_SNPRINTF(json+used,sizeof(json)-used,
            "%s{\"app_id\":%d,\"pid\":%d,\"title_id\":null,\"resolved\":false}",
            entries?",":"",(int)apps[i],(int)pid);
        else count=R_SNPRINTF(json+used,sizeof(json)-used,
            "%s{\"app_id\":%d,\"pid\":null,\"title_id\":null,\"resolved\":false}",
            entries?",":"",(int)apps[i]);
        if(count<0||(size_t)count>=sizeof(json)-used) return -1;
        used+=(size_t)count;entries++;
    }
    count=R_SNPRINTF(json+used,sizeof(json)-used,
        "],\"entries_reported\":%u,\"capacity_limited\":true,\"launch_policy\":\"unqualified_disabled\"}",entries);
    if(count<0||(size_t)count>=sizeof(json)-used) return -1;
    used+=(size_t)count;
    if(used>=capacity) return -1;
    R_MEMCPY(reply,json,used+1);return (int)used;
}
