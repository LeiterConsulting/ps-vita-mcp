#include "api.h"
#include "test_bootstrap_platform.h"
#include <assert.h>
int module_start(SceSize size,const void *arg);
static int calls,opened,written,published,open_error,short_write,close_error,rename_error,metadata_error,bad_build,ready;
static char path[168];
static int process_id=42;
int sceKernelGetProcessId(void) { return process_id; }
int vitaControlBootstrapInfo(RBootstrapInfo *out,unsigned size) {
    calls++;assert(size==112);
    if(metadata_error) return metadata_error;
    *out=(RBootstrapInfo){.magic=RC_BOOT_MAGIC,.abi=RC_ABI,.size=112,.ready=ready,.caller_before=42,.caller_after=42,.shell_pid=84};
    memcpy(out->build_id,R_BUILD_ID,65);if(bad_build) out->build_id[0]^=1;return 0;
}
int sceIoOpen(const char *name,int flags,int mode) {
    opened++;assert(flags==(SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL) && mode==(0600|SCE_S_IRSYS|SCE_S_IWSYS));
    snprintf(path,sizeof(path),"%s",name);return open_error?open_error:10;
}
int sceIoWrite(int fd,const void *data,unsigned size) { assert(fd==10 && size==112 && ((RBootstrapInfo *)data)->magic==RC_BOOT_MAGIC);written++;return short_write?111:112; }
int sceIoClose(int fd) { assert(fd==10);return close_error; }
int sceIoRename(const char *old_path,const char *new_path) { assert(strstr(old_path,".bin.part") && !strstr(new_path,".part"));if(rename_error) return rename_error;published++;return 0; }
static void reset(void) { calls=opened=written=published=open_error=short_write=close_error=rename_error=metadata_error=bad_build=0;ready=1;process_id=42;path[0]=0; }
int main(void) {
    RBootstrapArgs args={.magic=RC_BOOT_ARGS_MAGIC,.mode=1,.run="0123456789abcdef0123456789abcdef"};
    reset();assert(module_start(0,NULL)==0 && !calls && !opened);
    reset();assert(module_start(43,&args)==0 && !calls);
    reset();args.run[1]='/';assert(module_start(44,&args)==0 && !calls);args.run[1]='1';
    reset();args.padding[2]=1;assert(module_start(44,&args)==0 && !calls);args.padding[2]=0;
    reset();assert(module_start(44,&args)==0 && calls==1 && written==1 && published==1 && strstr(path,"/0123456789abcdef0123456789abcdef/bootstrap.bin.part"));
    reset();metadata_error=-123;assert(module_start(44,&args)==0 && !opened);
    reset();bad_build=1;assert(module_start(44,&args)==0 && !opened);
    reset();ready=0;assert(module_start(44,&args)==0 && !opened);
    reset();process_id=43;assert(module_start(44,&args)==0 && !opened);
    reset();open_error=-123;assert(module_start(44,&args)==0 && !written && !published);
    reset();short_write=1;assert(module_start(44,&args)==0 && written==1 && !published);
    reset();close_error=-123;assert(module_start(44,&args)==0 && !published);
    reset();rename_error=-123;assert(module_start(44,&args)==0 && !published);
    puts("13 actual bootstrap probe cases passed: invalid session, matched caller/build metadata, readiness and publication failures.");
}
