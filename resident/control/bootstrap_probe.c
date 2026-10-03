#include "api.h"
#ifdef RC_BOOT_HOST
#include "test_bootstrap_platform.h"
#else
#include <psp2/kernel/clib.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#endif
#ifndef RC_BOOT_HOST
void *memset(void *out,int value,size_t size) { return sceClibMemset(out,value,size); }
#endif
int module_start(SceSize size,const void *arg) {
    if(!rcValidBootArgs(size,arg)) return SCE_KERNEL_START_SUCCESS;
    const RBootstrapArgs *args=arg;RBootstrapInfo info={0};
    if(vitaControlBootstrapInfo(&info,sizeof(info))!=0 || info.magic!=RC_BOOT_MAGIC || info.abi!=RC_ABI ||
       info.size!=sizeof(info) || info.ready!=1 || info.shell_pid<=0 || info.caller_before!=sceKernelGetProcessId() ||
       info.caller_after!=info.caller_before || info.shell_pid==info.caller_after || info.guard_allowed || info.build_id[64] || sceClibStrcmp(info.build_id,R_BUILD_ID))
        return SCE_KERNEL_START_SUCCESS;
    char path[160],part[168];
    sceClibSnprintf(path,sizeof(path),RC_BOOT_ROOT "/%s/bootstrap.bin",args->run);
    sceClibSnprintf(part,sizeof(part),"%s.part",path);
    int fd=sceIoOpen(part,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(fd>=0) {
        int written=sceIoWrite(fd,&info,sizeof(info)),closed=sceIoClose(fd);
        if(written==(int)sizeof(info) && closed>=0) sceIoRename(part,path);
    }
    return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize size,const void *arg) { (void)size;(void)arg;return SCE_KERNEL_STOP_SUCCESS; }
int _start(SceSize size,const void *arg) __attribute__((weak,alias("module_start")));
