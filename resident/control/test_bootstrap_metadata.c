#include "api.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int caller=42,shell=84,copy_failure,ready=1,copies;
int ksceKernelGetProcessId(void) { return caller; }
int ksceKernelSysrootGetShellPid(void) { return shell; }
uint64_t ksceKernelGetSystemTimeWide(void) { return 123456; }
int rc_bootstrap_ready(void) { return ready; }
int ksceKernelCopyToUser(void *out,const void *source,unsigned size) {
    copies++;if(copy_failure) return copy_failure;
    memcpy(out,source,size);return 0;
}
int main(void) {
    RBootstrapInfo info;
    assert(vitaControlBootstrapInfo(&info,sizeof(info))==0 && info.magic==RC_BOOT_MAGIC && info.size==112 && info.abi==RC_ABI && info.ready==1);
    assert(info.caller_before==42 && info.caller_after==42 && info.shell_pid==84 && !info.guard_allowed && !strcmp(info.build_id,R_BUILD_ID));
    caller=shell;assert(vitaControlBootstrapInfo(&info,112)==0 && info.guard_allowed);
    caller=shell=0;assert(vitaControlBootstrapInfo(&info,112)==0 && !info.guard_allowed);
    caller=shell=-1;assert(vitaControlBootstrapInfo(&info,112)==0 && !info.guard_allowed);
    ready=0;assert(vitaControlBootstrapInfo(&info,112)==0 && !info.ready);
    int count=copies;assert(vitaControlBootstrapInfo(NULL,112)==(int32_t)0x80020005u && vitaControlBootstrapInfo(&info,111)==(int32_t)0x80020005u && vitaControlBootstrapInfo(&info,113)==(int32_t)0x80020005u && copies==count);
    memset(&info,0x5a,sizeof(info));copy_failure=-123;assert(vitaControlBootstrapInfo(&info,112)==-123 && info.magic==0x5a5a5a5a);
    puts("PASS: actual bootstrap metadata; exact size/null/copy errors, readiness and positive Shell caller guard. SDK calls simulated.");
}
