#include "native.h"
#include "test_native_platform.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks,rng_calls,list_calls,pid_calls,name_calls;
static int rng_result,random_zero,reenter_rng,list_result,pid_result=123,name_result;
static SceInt32 slots[16];
static char title_value[32]="CHRS00003";

static void check(int condition) { assert(condition);checks++; }
uint64_t r_pair_mono(void) { return 9876543210ULL; }
int r_pair_random(void *out,size_t bytes) {
    rng_calls++;assert(bytes==16);
    if(reenter_rng) { char concurrent[33]="unchanged";check(lb_native_instance(concurrent)==0&&concurrent[0]==0); }
    for(unsigned i=0;i<bytes;i++) ((unsigned char *)out)[i]=random_zero?0:(unsigned char)(0xf0u+i);
    return rng_result;
}
int sceAppMgrGetRunningAppIdListForShell(SceInt32 *apps,int capacity) {
    list_calls++;assert(capacity==16);memcpy(apps,slots,sizeof(slots));return list_result;
}
SceUID sceAppMgrGetProcessIdByAppIdForShell(SceInt32 app) {
    pid_calls++;assert(app>0);return pid_result;
}
int sceAppMgrGetNameById(SceUID pid,char *title) {
    name_calls++;assert(pid>0);memcpy(title,title_value,32);return name_result;
}

static void identity_test(int kind) {
    char out[33]="old-output",again[33]="old-output";
    check(lb_native_instance(0)==0&&rng_calls==0);
    if(kind==1) rng_result=-42;
    if(kind==2) rng_result=1;
    if(kind==3) random_zero=1;
    if(kind==4) reenter_rng=1;
    int result=lb_native_instance(out);
    if(kind==0||kind==4) {
        check(result==1);check(strcmp(out,"f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")==0);
        check(lb_native_instance(again)==1&&strcmp(again,out)==0);
    } else {
        check(result==0&&out[0]==0);
        rng_result=0;random_zero=0;
        check(lb_native_instance(again)==0&&again[0]==0);
    }
    check(rng_calls==1);
    printf("native identity case %d: %u checks\n",kind,checks);
}

static void child_identity(int kind) {
    pid_t child=fork();assert(child>=0);
    if(child==0) { checks=0;identity_test(kind);fflush(stdout);_exit(0); }
    int status=0;assert(waitpid(child,&status,0)==child);check(WIFEXITED(status)&&WEXITSTATUS(status)==0);
}

int main(void) {
    for(int kind=0;kind<5;kind++) child_identity(kind);
    check(lb_native_now(0)==9876543210ULL);
    check(lb_native_now((void *)1)==9876543210ULL);
    unsigned before=list_calls+pid_calls+name_calls+rng_calls;
    for(unsigned i=0;i<4;i++) {
        LBLaunchResult result=lb_native_launch((void *)(uintptr_t)i);
        check(result.confirmed==0&&result.result==LB_NATIVE_LAUNCH_UNQUALIFIED);
    }
    check(before==list_calls+pid_calls+name_calls+rng_calls);

    char reply[LB_NATIVE_INVENTORY_CAPACITY];
    check(lb_native_inventory(0,sizeof(reply))<0&&list_calls==0);
    check(lb_native_inventory(reply,0)<0&&list_calls==0);
    int count=lb_native_inventory(reply,sizeof(reply));
    check(count>0&&(size_t)count==strlen(reply));
    check(strstr(reply,"\"entries\":[]")!=0&&pid_calls==0&&name_calls==0);
    check(strstr(reply,"\"foreground_verified\":false")!=0);
    check(strstr(reply,"\"protected_ui_verified\":false")!=0);
    check(strstr(reply,"\"native_submission_enabled\":false")!=0);
    check(strstr(reply,"\"sampled_ms\":9876543210")!=0);
    check(strstr(reply,"\"snapshot_atomic\":false")!=0);

    slots[15]=101;list_result=0;
    check(lb_native_inventory(reply,sizeof(reply))>0);
    check(strstr(reply,"\"app_id\":101,\"pid\":123,\"title_id\":\"CHRS00003\"")!=0);
    check(pid_calls==1&&name_calls==1);
    list_result=1;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"entries_reported\":1")!=0);
    slots[0]=101;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"entries_reported\":1")!=0);
    slots[1]=-7;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"entries_reported\":1")!=0);
    for(unsigned i=0;i<16;i++) slots[i]=(int)i+1;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"entries_reported\":16")!=0);

    memset(slots,0,sizeof(slots));slots[0]=101;
    const char *invalid_titles[]={"bad-title","CHRS0000\"","CHRS00003X","CHRS0000\n","CHRS0000\\"};
    for(unsigned i=0;i<sizeof(invalid_titles)/sizeof(invalid_titles[0]);i++) {
        memset(title_value,0,sizeof(title_value));strcpy(title_value,invalid_titles[i]);
        check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"title_id\":null,\"resolved\":false")!=0);
        check(strstr(reply,invalid_titles[i])==0);
    }
    memset(title_value,'X',sizeof(title_value));
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"title_id\":null")!=0);
    strcpy(title_value,"NPXS10079");name_result=-1;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"NPXS10079")==0);
    name_result=0;pid_result=0;before=name_calls;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"pid\":null")!=0&&name_calls==before);
    pid_result=-10;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"pid\":null")!=0&&name_calls==before);
    pid_result=123;list_result=-20;before=pid_calls;
    check(lb_native_inventory(reply,sizeof(reply))>0&&strstr(reply,"\"available\":false")!=0);
    check(strstr(reply,"\"enumeration_result\":-20")!=0&&pid_calls==before);
    check(strstr(reply,"\"entries\":[]")!=0);
    list_result=0;
    count=lb_native_inventory(reply,sizeof(reply));check(count>0);
    char exact[LB_NATIVE_INVENTORY_CAPACITY];
    check(lb_native_inventory(exact,(size_t)count)<0&&exact[0]==0);
    check(lb_native_inventory(exact,(size_t)count+1)==count&&exact[count]==0);
    check(lb_native_inventory(exact,1)<0&&exact[0]==0);
    LBLaunchResult after_inventory=lb_native_launch(0);
    check(after_inventory.confirmed==0&&after_inventory.result==LB_NATIVE_LAUNCH_UNQUALIFIED);
    puts(reply);
    printf("native inventory/refusal: %u parent checks plus isolated identity checks passed\n",checks);
    return 0;
}
