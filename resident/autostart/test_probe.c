#include "autostart.h"
#include "test_probe_platform.h"
#include <assert.h>
#define BUILD "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
int module_start(SceSize size,const void *arg);
static int calls,opens,writes,renames,copy_error,open_error,short_write,close_error,rename_error,own_pid;
static RBootstrapInfo metadata;
static void reset(void) {
    calls=opens=writes=renames=copy_error=open_error=short_write=close_error=rename_error=0;own_pid=84;
    metadata=(RBootstrapInfo){.magic=RC_BOOT_MAGIC,.abi=RC_ABI,.size=112,.ready=1,.caller_before=84,.caller_after=84,.shell_pid=84,.guard_allowed=1};
    memcpy(metadata.build_id,BUILD,65);
}
int vitaControlBootstrapInfo(RBootstrapInfo *out,unsigned size) { assert(size==112);calls++;*out=metadata;return copy_error; }
int sceKernelGetProcessId(void) { return own_pid; }
int sceIoOpen(const char *path,int flags,int mode) {
    assert(strstr(path,"vita-autostart/0123456789abcdef0123456789abcdef/bootstrap.bin.part"));
    assert(flags==(SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL) && mode==(0600|SCE_S_IRSYS|SCE_S_IWSYS));
    opens++;return open_error ? -1 : 10;
}
int sceIoWrite(int fd,const void *bytes,unsigned size) { assert(fd==10 && size==112 && ((RBootstrapInfo *)bytes)->guard_allowed==1);writes++;return short_write ? 111 : 112; }
int sceIoClose(int fd) { assert(fd==10);return close_error; }
int sceIoRename(const char *from,const char *to) { assert(strstr(from,".part") && !strstr(to,".part"));if(rename_error)return -1;renames++;return 0; }
int main(void) {
    RBootstrapArgs args={.magic=RC_BOOT_ARGS_MAGIC,.mode=1,.run="0123456789abcdef0123456789abcdef"};
    reset();assert(module_start(0,0)==0 && !calls && !opens);
    reset();args.mode=2;assert(module_start(44,&args)==0 && !calls);args.mode=1;
    reset();args.run[0]='/';assert(module_start(44,&args)==0 && !calls);args.run[0]='0';
    reset();assert(module_start(44,&args)==0 && calls==1 && writes==1 && renames==1);
    reset();own_pid=42;assert(module_start(44,&args)==0 && !opens);
    reset();metadata.guard_allowed=0;assert(module_start(44,&args)==0 && !opens);
    reset();metadata.shell_pid=0;assert(module_start(44,&args)==0 && !opens);
    reset();metadata.build_id[0]='f';assert(module_start(44,&args)==0 && !opens);
    reset();copy_error=-1;assert(module_start(44,&args)==0 && !opens);
    reset();open_error=1;assert(module_start(44,&args)==0 && !writes && !renames);
    reset();short_write=1;assert(module_start(44,&args)==0 && writes==1 && !renames);
    reset();close_error=-1;assert(module_start(44,&args)==0 && !renames);
    reset();rename_error=-1;assert(module_start(44,&args)==0 && !renames);
    puts("PASS: actual Shell-only probe, 13 guarded publication cases; SDK calls simulated.");return 0;
}
