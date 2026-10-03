#include "api.h"
#ifdef VI_HOST
#include "test_proxy_platform.h"
#else
#include <psp2/kernel/clib.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#endif

#ifndef VI_HOST
void *memset(void *out,int value,size_t size) { return sceClibMemset(out,value,size); }
#endif
static char entry_path[120];
static unsigned entry_bytes;
static void journal(const char *stage,int result) {
    if(entry_bytes>=2048) return;
    char line[160];
    int n=sceClibSnprintf(line,sizeof(line),"stage=%s result=0x%08x\n",stage,(unsigned)result);
    if(n<=0 || (unsigned)n>=sizeof(line)) return;
    int fd=sceIoOpen(entry_path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(fd>=0) { int written=sceIoWrite(fd,line,(unsigned)n); sceIoClose(fd); if(written>0) entry_bytes+=(unsigned)written; }
}
int module_start(SceSize size,const void *arg) {
    /* A diagnostic failure is data, and must never fail SceShell startup. */
    sceClibSnprintf(entry_path,sizeof(entry_path),"ux0:data/vita-control-inspector/proxy-entry-%08x.log",(unsigned)sceKernelGetProcessId());
    entry_bytes=0;
    int entry=sceIoOpen(entry_path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_TRUNC,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(entry>=0) { sceIoWrite(entry,"inspector_version=" VI_VERSION "\nbuild_id=" VI_BUILD_ID "\n",sizeof("inspector_version=" VI_VERSION "\nbuild_id=" VI_BUILD_ID "\n")-1); sceIoClose(entry); }
    journal("module entry args size",(int)size);
    journal("module entry arg present",arg?1:0);
    VIArgs session={0};
    const VIArgs *args=arg;
    int shared_session=size==0;
    if(shared_session) {
        /* A no-argument Shell entry uses the immutable, fresh session guard
           written by the Inspector before its one kernel load this boot. */
        int fd=sceIoOpen(VI_SESSION_PATH,SCE_O_RDONLY,0);
        journal("Shell session record open",fd);
        if(fd<0) return SCE_KERNEL_START_SUCCESS;
        int read=sceIoRead(fd,&session,sizeof(session));
        unsigned char extra=0;
        int tail=read==(int)sizeof(session)?sceIoRead(fd,&extra,1):-1;
        int closed=sceIoClose(fd);
        journal("Shell session record read",read);journal("Shell session record tail",tail);journal("Shell session record close",closed);
        if(read!=(int)sizeof(session) || tail!=0 || closed<0 || !viValidArgs(sizeof(session),&session) || session.mode!=1) {
            journal("Shell session record rejected",VI_E_ARGUMENT);return SCE_KERNEL_START_SUCCESS;
        }
        session.mode=2;args=&session;size=sizeof(session);
    }
    if(!viValidArgs(size,args)) { journal("argument validation failed",-1); return SCE_KERNEL_START_SUCCESS; }
    journal("argument validation passed",(int)args->mode);
    char nonce_line[64];int nonce_size=sceClibSnprintf(nonce_line,sizeof(nonce_line),"run_nonce=%s\n",args->run);
    int nonce_fd=sceIoOpen(entry_path,SCE_O_WRONLY|SCE_O_APPEND,0);
    if(nonce_fd>=0) { if(nonce_size>0 && (unsigned)nonce_size<sizeof(nonce_line)) sceIoWrite(nonce_fd,nonce_line,(unsigned)nonce_size);sceIoClose(nonce_fd); }
    VIInfo info={0}; char build[65]={0}, guarded[65]={0};
    journal("calling version",0);
    int version=viVersion();
    journal("version",version);
    int info_result=viInfo(&info,sizeof(info));
    journal("info",info_result);
    if(shared_session && (info_result!=0 || info.magic!=VI_MAGIC || info.abi!=VI_ABI || info.size!=sizeof(info) ||
        info.shell_pid<=0 || info.shell_pid!=sceKernelGetProcessId() || info.caller_before!=info.shell_pid ||
        info.caller_after!=info.shell_pid || info.guard_allowed!=1)) {
        journal("Shell session caller rejected",VI_E_DENIED);return SCE_KERNEL_START_SUCCESS;
    }
    int build_result=viBuildId(build,sizeof(build));
    journal("build identity",build_result);
    int guard_result=viShellBuildId(guarded,sizeof(guarded));
    journal("guarded identity",guard_result);
    int invalid_size_result=viBuildId(build,64);
    journal("invalid size test",invalid_size_result);
    int matched=build_result>=0 && !sceClibStrcmp(build,VI_BUILD_ID);
    int guard_matched=guard_result>=0 && !sceClibStrcmp(guarded,VI_BUILD_ID);
    char path[160],temporary[168],report[1600];
    sceClibSnprintf(path,sizeof(path),"ux0:data/vita-control-inspector/%s/%s.log",args->run,args->mode==1?"self":"shell");
    sceClibSnprintf(temporary,sizeof(temporary),"%s.part",path);
    int n=sceClibSnprintf(report,sizeof(report),
        "inspector_version=" VI_VERSION "\nbuild_id=%s\nmode=%u\nuser_pid=0x%08x\nabi=%d\ninfo_result=0x%08x\ninfo_magic=0x%08x\ninfo_size=%u\ncaller_before=0x%08x\ncaller_after=0x%08x\nshell_pid=0x%08x\nguard_allowed=%d\nbuild_result=0x%08x\nbuild_matched=%d\nguard_result=0x%08x\nguard_matched=%d\ninvalid_size_result=0x%08x\ntick_us=%llu\n",
        VI_BUILD_ID,args->mode,(unsigned)sceKernelGetProcessId(),version,(unsigned)info_result,info.magic,info.size,(unsigned)info.caller_before,(unsigned)info.caller_after,(unsigned)info.shell_pid,info.guard_allowed,(unsigned)build_result,matched,(unsigned)guard_result,guard_matched,(unsigned)invalid_size_result,(unsigned long long)info.tick_us);
    if(n>0 && (unsigned)n<sizeof(report)) {
        int fd=sceIoOpen(temporary,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
        journal("report open",fd);
        if(fd>=0) {
            int written=sceIoWrite(fd,report,(unsigned)n); int closed=sceIoClose(fd); journal("report write",written); journal("report close",closed);
            if(written==n && closed>=0) journal("report publish",sceIoRename(temporary,path));
            else journal("incomplete report retained as part",-1);
        }
    } else journal("report formatting failed",n);
    journal("diagnostic finished",0);
    return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize size,const void *args) { (void)size; (void)args; return SCE_KERNEL_STOP_SUCCESS; }
int _start(SceSize size,const void *args) __attribute__((weak,alias("module_start")));
