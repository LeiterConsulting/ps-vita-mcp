#include "api.h"
#include <string.h>
#ifdef RC_BOOT_HOST
#define ENTER_SYSCALL(s) do { (s)=0; } while(0)
#define EXIT_SYSCALL(s) do { (void)(s); } while(0)
int ksceKernelGetProcessId(void);
int ksceKernelSysrootGetShellPid(void);
uint64_t ksceKernelGetSystemTimeWide(void);
int ksceKernelCopyToUser(void *out,const void *src,unsigned size);
#else
#include <psp2kern/kernel/cpu.h>
#include <psp2kern/kernel/sysroot.h>
#include <psp2kern/kernel/threadmgr.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>
#include <psp2/kernel/error.h>
#endif
int rc_bootstrap_ready(void);
int vitaControlBootstrapInfo(RBootstrapInfo *out,unsigned size) {
    int before=ksceKernelGetProcessId(),state,result=(int32_t)0x80020005u;
    ENTER_SYSCALL(state);
    if(out && size==sizeof(RBootstrapInfo)) {
        RBootstrapInfo info={0};
        info.magic=RC_BOOT_MAGIC;info.abi=RC_ABI;info.size=sizeof(info);info.ready=rc_bootstrap_ready();
        info.caller_before=before;info.caller_after=ksceKernelGetProcessId();info.shell_pid=ksceKernelSysrootGetShellPid();
        info.guard_allowed=info.caller_after>0 && info.shell_pid>0 && info.caller_after==info.shell_pid;
        info.tick_us=ksceKernelGetSystemTimeWide();memcpy(info.build_id,R_BUILD_ID,65);
        result=ksceKernelCopyToUser(out,&info,sizeof(info));
    }
    EXIT_SYSCALL(state);return result;
}
