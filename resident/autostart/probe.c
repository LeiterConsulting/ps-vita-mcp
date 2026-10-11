#include "autostart.h"
#ifdef AO_PROBE_HOST
#include "test_probe_platform.h"
#else
#include <psp2/kernel/clib.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
void *memset(void *out,int value,size_t size) { return sceClibMemset(out,value,size); }
void *memcpy(void *out,const void *source,size_t size) { return sceClibMemcpy(out,source,size); }
#endif

int module_start(SceSize size,const void *arg) {
    if(!rcValidBootArgs(size,arg)) return SCE_KERNEL_START_SUCCESS;
    const RBootstrapArgs *args=arg;
    AOProbe probe={.module_id=1,.start_result=0};
    probe.metadata_result=vitaControlBootstrapInfo(&probe.info,sizeof(probe.info));
    if(!ao_valid_metadata(&probe,sceKernelGetProcessId(),CONTROL_BUILD_ID))
        return SCE_KERNEL_START_SUCCESS;
    char path[160],part[168];
    sceClibSnprintf(path,sizeof(path),AO_ROOT "/%s/bootstrap.bin",args->run);
    sceClibSnprintf(part,sizeof(part),"%s.part",path);
    int fd=sceIoOpen(part,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(fd>=0) {
        int written=sceIoWrite(fd,&probe.info,sizeof(probe.info)),closed=sceIoClose(fd);
        if(written==(int)sizeof(probe.info) && closed>=0) sceIoRename(part,path);
    }
    return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize size,const void *arg) { (void)size;(void)arg;return SCE_KERNEL_STOP_SUCCESS; }
int _start(SceSize size,const void *arg) __attribute__((weak,alias("module_start")));
