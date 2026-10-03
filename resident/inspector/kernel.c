#include "api.h"
#include <string.h>
#ifdef VI_HOST
typedef unsigned SceSize;
#define SCE_KERNEL_START_SUCCESS 0
#define SCE_KERNEL_STOP_SUCCESS 0
#define ENTER_SYSCALL(s) do { (s)=0; } while(0)
#define EXIT_SYSCALL(s) do { (void)(s); } while(0)
int ksceKernelGetProcessId(void);
int ksceKernelSysrootGetShellPid(void);
uint64_t ksceKernelGetSystemTimeWide(void);
int ksceKernelCopyToUser(void *out, const void *src, unsigned size);
#else
#include <psp2kern/kernel/modulemgr.h>
#include <psp2kern/kernel/cpu.h>
#include <psp2kern/kernel/sysroot.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>
#include <psp2kern/kernel/threadmgr.h>
#include <psp2/kernel/error.h>
_Static_assert((uint32_t)VI_E_ARGUMENT==SCE_KERNEL_ERROR_INVALID_ARGUMENT,"SDK argument error identity");
_Static_assert((uint32_t)VI_E_DENIED==SCE_KERNEL_ERROR_ILLEGAL_PERMISSION,"SDK permission error identity");
#endif

int viVersion(void) { return VI_ABI; }
int viInfo(VIInfo *out, unsigned size) {
    int before=ksceKernelGetProcessId(), state, result=VI_E_ARGUMENT;
    ENTER_SYSCALL(state);
    if(out && size==sizeof(VIInfo)) {
        VIInfo value;
        memset(&value,0,sizeof(value));
        value.magic=VI_MAGIC; value.abi=VI_ABI; value.size=sizeof(value);
        value.caller_before=before; value.caller_after=ksceKernelGetProcessId();
        value.shell_pid=ksceKernelSysrootGetShellPid();
        value.guard_allowed=value.caller_after>0 && value.shell_pid>0 && value.caller_after==value.shell_pid;
        value.tick_us=ksceKernelGetSystemTimeWide();
        memcpy(value.build_id,VI_BUILD_ID,65);
        result=ksceKernelCopyToUser(out,&value,sizeof(value));
    }
    EXIT_SYSCALL(state); return result;
}
static int identity(char *out, unsigned size, int guarded) {
    int state, result=VI_E_ARGUMENT; ENTER_SYSCALL(state);
    int caller=ksceKernelGetProcessId(), shell=ksceKernelSysrootGetShellPid();
    if(out && size==65) {
        if(guarded && !(caller>0 && shell>0 && caller==shell)) result=VI_E_DENIED;
        else result=ksceKernelCopyToUser(out,VI_BUILD_ID,65);
    }
    EXIT_SYSCALL(state); return result;
}
int viBuildId(char *out, unsigned size) { return identity(out,size,0); }
int viShellBuildId(char *out, unsigned size) { return identity(out,size,1); }
/* Deliberately no hooks, threads, mutexes, networking, file writes, or display calls. */
int module_start(SceSize size, const void *args) { (void)size; (void)args; return SCE_KERNEL_START_SUCCESS; }
int module_stop(SceSize size, const void *args) { (void)size; (void)args; return SCE_KERNEL_STOP_SUCCESS; }
int _start(SceSize size,const void *args) __attribute__((weak,alias("module_start")));
