#include "api.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int caller=42,shell=84,copy_failure;
int ksceKernelGetProcessId(void) { return caller; }
int ksceKernelSysrootGetShellPid(void) { return shell; }
uint64_t ksceKernelGetSystemTimeWide(void) { return 123456; }
int ksceKernelCopyToUser(void *out,const void *source,unsigned size) {
    if(copy_failure) return copy_failure;
    memcpy(out,source,size); return 0;
}
int main(void) {
    VIInfo info; char build[65]; memset(build,'x',sizeof(build));
    assert(viVersion()==VI_ABI);
    assert(viInfo(&info,sizeof(info))==0 && info.magic==VI_MAGIC && info.size==112);
    assert(info.caller_before==42 && info.caller_after==42 && info.shell_pid==84 && !info.guard_allowed);
    assert(viBuildId(build,65)==0 && !strcmp(build,VI_BUILD_ID));
    memset(build,'x',65); assert(viShellBuildId(build,65)==VI_E_DENIED && build[0]=='x');
    caller=shell; assert(viShellBuildId(build,65)==0 && !strcmp(build,VI_BUILD_ID));
    assert(viInfo(&info,sizeof(info))==0 && info.guard_allowed);
    caller=shell=0; assert(viShellBuildId(build,65)==VI_E_DENIED);
    caller=shell=-1; assert(viShellBuildId(build,65)==VI_E_DENIED);
    memset(build,'x',65);
    assert(viInfo(NULL,112)==VI_E_ARGUMENT && viInfo(&info,111)==VI_E_ARGUMENT);
    assert(viBuildId(NULL,65)==VI_E_ARGUMENT && viBuildId(build,64)==VI_E_ARGUMENT && viBuildId(build,66)==VI_E_ARGUMENT);
    assert(build[0]=='x');
    caller=shell=84; copy_failure=-123;
    assert(viInfo(&info,112)==-123 && viBuildId(build,65)==-123 && viShellBuildId(build,65)==-123);
    puts("PASS: actual metadata syscall implementation; caller guard, exact buffer size, null pointers, build identity and unchanged copy errors. SDK calls simulated.");
}
