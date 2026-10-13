#include "native_launch.h"
#include "../platform.h"
#ifdef NL_HOST_TEST
#include "test_platform.h"
#else
#include <psp2/appmgr.h>
#endif

typedef struct {
    int result,enumeration_result,occupied;
    unsigned system_events,app_events;
    int overlay,state_result;
} Policy;

static int fixed_title(const char *title) { return title&&!R_STRCMP(title,NL_TITLE); }
static int build_valid(const char *build) {
    if(!build||R_STRLEN(build)!=64)return 0;
    for(unsigned n=0;n<64;n++)
        if(!((build[n]>='a'&&build[n]<='f')||(build[n]>='0'&&build[n]<='9')))return 0;
    return 1;
}
static int title_valid(const char title[32]) {
    for(unsigned n=0;n<9;n++)
        if(!((title[n]>='A'&&title[n]<='Z')||(title[n]>='0'&&title[n]<='9')))return 0;
    return title[9]==0;
}
static int inventory(Policy *p,const char *wanted,int32_t *found) {
    SceInt32 apps[16]={0};*found=0;
    p->enumeration_result=sceAppMgrGetRunningAppIdListForShell(apps,16);
    if(p->enumeration_result<0)return NL_ENUMERATION;
    if(p->enumeration_result>=16)return NL_CAPACITY;
    for(unsigned n=0;n<16;n++) {
        if(!apps[n])continue;
        p->occupied++;
        if(apps[n]<0)return NL_UNRESOLVED;
        SceUID pid=sceAppMgrGetProcessIdByAppIdForShell(apps[n]);
        char title[32]={0};
        if(pid<=0||sceAppMgrGetNameById(pid,title)<0||!title_valid(title))return NL_UNRESOLVED;
        if(!R_STRCMP(title,wanted)) {
            if(*found&&*found!=pid)return NL_UNRESOLVED;
            *found=pid;
        }
    }
    if(p->occupied>=16)return NL_CAPACITY;
    /* Pinned SDK declares the return value to be the application count.
       An inconsistent array/count cannot prove that the Shell is idle. */
    return p->occupied==p->enumeration_result?0:NL_UNRESOLVED;
}
static int idle(Policy *p) {
    R_MEMSET(p,0,sizeof(*p));int32_t found;
    p->result=inventory(p,NL_TITLE,&found);
    if(p->result)return p->result;
    if(p->occupied)return p->result=NL_APP_RUNNING;
    /* This is the calling Shell process's pending-event/overlay state, not a
       system-wide display attestation. Never drain Shell's event queue here. */
    for(unsigned n=0;n<2;n++) {
        SceAppMgrAppState state;R_MEMSET(&state,0xff,sizeof(state));
        p->state_result=_sceAppMgrGetAppState(&state,sizeof(state),1);
        if(p->state_result<0)return p->result=NL_STATE_UNAVAILABLE;
        p->system_events=state.systemEventNum;p->app_events=state.appEventNum;
        p->overlay=(int)state.isSystemUiOverlaid;
        if(p->overlay!=0&&p->overlay!=1)return p->result=NL_STATE_INVALID;
        if(p->overlay)return p->result=NL_OVERLAY;
        if(p->system_events||p->app_events)return p->result=NL_EVENTS;
    }
    return 0;
}
int nl_idle_policy(const char *title,int absent) {
    if(!fixed_title(title)||absent!=1)return NL_INVALID;
    Policy p;return idle(&p);
}
int nl_idle_ready(void) { return nl_idle_policy(NL_TITLE,1); }
int nl_target_absent(const char *title) {
    if(!fixed_title(title))return NL_INVALID;
    Policy p={0};int32_t found;int result=inventory(&p,title,&found);
    return result?result:found?1:0;
}
int nl_inventory_pid(const char *title,int32_t *pid) {
    if(pid)*pid=0;
    if(!fixed_title(title)||!pid)return NL_INVALID;
    Policy p={0};int result=inventory(&p,title,pid);
    if(result){*pid=0;return result;}
    return *pid?0:NL_NOT_RUNNING;
}
int nl_policy_status(char *reply,size_t capacity) {
    if(!reply||!capacity)return -1;
    reply[0]=0;Policy p;idle(&p);
    int n=R_SNPRINTF(reply,capacity,
        "{\"app\":\"Vita Native Launch Policy\",\"protocol\":1,\"policy\":\"idle_shell_only\","
        "\"title_id\":\"" NL_TITLE "\",\"ready\":%s,\"result\":%d,\"enumeration_result\":%d,"
        "\"occupied_slots\":%d,\"state_result\":%d,\"system_events\":%u,\"app_events\":%u,"
        "\"overlay\":%d,\"state_samples_required\":2,\"snapshot_atomic\":false,"
        "\"foreground_verified\":false,\"protected_ui_verified\":false,\"native_submission_enabled\":true}",
        p.result==0?"true":"false",p.result,p.enumeration_result,p.occupied,
        p.state_result,p.system_events,p.app_events,p.overlay);
    if(n<0||(size_t)n>=capacity){reply[0]=0;return -1;}
    return n;
}
NLLaunchResult nl_launch_owned_result(const char *title,const char *build) {
    NLLaunchResult result={0,NL_INVALID};
    if(!fixed_title(title)||!build_valid(build))return result;
    result.result=nl_idle_policy(title,1);
    if(result.result)return result;
    result.native_invoked=1;
    result.result=sceAppMgrLaunchAppByUri(0x20000,"psgm:play?titleid=" NL_TITLE);
    return result;
}
int nl_launch_owned(const char *title,const char *build) { return nl_launch_owned_result(title,build).result; }
NLLaunchResult nl_launch_lab(const char *build) { return nl_launch_owned_result(NL_TITLE,build); }
