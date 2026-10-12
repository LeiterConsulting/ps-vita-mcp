#include "native_launch.h"
#include "test_platform.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned checks,enumerations,state_calls,launches,names,pids;
static int list_result,state_result,launch_result,pid_result,name_result,change_at;
static SceInt32 slots[16];
static SceAppMgrAppState state;
static char title[32];
static void check(int value){assert(value);checks++;}
static void reset(void) {
    enumerations=state_calls=launches=names=pids=0;
    list_result=state_result=launch_result=name_result=change_at=0;pid_result=77;
    memset(slots,0,sizeof(slots));memset(&state,0,sizeof(state));
    memset(title,0,sizeof(title));strcpy(title,NL_TITLE);
}
int sceAppMgrGetRunningAppIdListForShell(SceInt32 *out,int count) {
    check(count==16);enumerations++;memcpy(out,slots,sizeof(slots));return list_result;
}
SceUID sceAppMgrGetProcessIdByAppIdForShell(SceInt32 id){check(id>0);pids++;return pid_result;}
int sceAppMgrGetNameById(SceUID id,char *out){check(id>0);names++;memcpy(out,title,sizeof(title));return name_result;}
int _sceAppMgrGetAppState(SceAppMgrAppState *out,SceSize size,uint32_t version) {
    check(size==128&&version==1);state_calls++;
    if(change_at&&(int)state_calls==change_at)state.isSystemUiOverlaid=1;
    memcpy(out,&state,sizeof(state));return state_result;
}
int sceAppMgrLaunchAppByUri(int flags,const char *uri) {
    check(flags==0x20000&&!strcmp(uri,"psgm:play?titleid=" NL_TITLE));launches++;return launch_result;
}
int main(void) {
    const char build[]="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    reset();check(nl_idle_ready()==0&&state_calls==2&&enumerations==1&&!launches);
    NLLaunchResult result=nl_launch_lab(build);
    check(result.native_invoked==1&&result.result==0&&launches==1&&state_calls==4);
    launch_result=-123;result=nl_launch_owned_result(NL_TITLE,build);
    check(result.native_invoked==1&&result.result==-123&&launches==2);
    launch_result=5;check(nl_launch_owned(NL_TITLE,build)==5&&launches==3);
    const char *bad_builds[]={"","ABC","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaG"};
    for(unsigned n=0;n<3;n++)check(!nl_launch_lab(bad_builds[n]).native_invoked&&launches==3);
    check(nl_idle_policy("CHRS00003",1)==NL_INVALID);
    check(nl_idle_policy(NL_TITLE,0)==NL_INVALID);
    check(nl_idle_policy(0,1)==NL_INVALID);
    check(nl_launch_owned("CHRS00003",build)==NL_INVALID&&launches==3);

    reset();list_result=-1;check(nl_idle_ready()==NL_ENUMERATION&&!state_calls);
    list_result=16;check(nl_idle_ready()==NL_CAPACITY&&!pids);
    list_result=17;check(nl_idle_ready()==NL_CAPACITY&&!pids);
    reset();list_result=1;check(nl_idle_ready()==NL_UNRESOLVED&&!state_calls);
    reset();list_result=2;slots[15]=42;check(nl_idle_ready()==NL_UNRESOLVED&&!state_calls);
    reset();list_result=1;slots[15]=42;check(nl_idle_ready()==NL_APP_RUNNING&&pids==1&&names==1&&!state_calls);
    check(nl_target_absent(NL_TITLE)==1);
    int32_t found=0;check(nl_inventory_pid(NL_TITLE,&found)==0&&found==77);
    strcpy(title,"NPXS10015");check(nl_target_absent(NL_TITLE)==0);
    check(nl_inventory_pid(NL_TITLE,&found)==NL_NOT_RUNNING&&!found);
    check(nl_idle_ready()==NL_APP_RUNNING);
    memset(title,'X',sizeof(title));check(nl_idle_ready()==NL_UNRESOLVED);
    strcpy(title,NL_TITLE);name_result=-1;check(nl_idle_ready()==NL_UNRESOLVED);
    name_result=0;pid_result=0;check(nl_idle_ready()==NL_UNRESOLVED);
    pid_result=-1;check(nl_idle_ready()==NL_UNRESOLVED);
    reset();slots[0]=-7;check(nl_idle_ready()==NL_UNRESOLVED);
    reset();for(unsigned n=0;n<16;n++)slots[n]=42;
    check(nl_idle_ready()==NL_CAPACITY);
    reset();check(nl_target_absent("BAD")==NL_INVALID&&nl_inventory_pid(NL_TITLE,0)==NL_INVALID);
    check(nl_target_absent(NL_TITLE)==0&&nl_inventory_pid(NL_TITLE,&found)==NL_NOT_RUNNING&&!found);

    reset();state_result=-1;check(nl_idle_ready()==NL_STATE_UNAVAILABLE&&state_calls==1);
    reset();state.isSystemUiOverlaid=2;check(nl_idle_ready()==NL_STATE_INVALID);
    reset();state.isSystemUiOverlaid=-1;check(nl_idle_ready()==NL_STATE_INVALID);
    reset();state.isSystemUiOverlaid=1;check(nl_idle_ready()==NL_OVERLAY);
    reset();state.systemEventNum=1;check(nl_idle_ready()==NL_EVENTS);
    reset();state.appEventNum=1;check(nl_idle_ready()==NL_EVENTS);
    reset();change_at=2;result=nl_launch_lab(build);
    check(result.result==NL_OVERLAY&&!result.native_invoked&&!launches&&state_calls==2);
    /* A preflight approval does not authorize the later callback after drift. */
    reset();check(nl_idle_ready()==0);state.isSystemUiOverlaid=1;
    result=nl_launch_lab(build);check(result.result==NL_OVERLAY&&!result.native_invoked&&!launches);
    reset();check(nl_idle_ready()==0);list_result=1;slots[15]=42;
    result=nl_launch_lab(build);check(result.result==NL_APP_RUNNING&&!result.native_invoked&&!launches);
    reset();char json[NL_POLICY_REPLY_MAX];
    check(nl_policy_status(json,sizeof(json))>0);
    check(strstr(json,"\"ready\":true")&&strstr(json,"\"foreground_verified\":false")&&strstr(json,"\"protected_ui_verified\":false"));
    check(nl_policy_status(json,1)<0&&!json[0]);check(nl_policy_status(0,sizeof(json))<0);
    reset();state.appEventNum=1;check(nl_policy_status(json,sizeof(json))>0&&strstr(json,"\"ready\":false"));
    printf("native idle policy and fixed URI: %u assertions passed; SDK calls mocked, no device acceptance\n",checks);
    return 0;
}
