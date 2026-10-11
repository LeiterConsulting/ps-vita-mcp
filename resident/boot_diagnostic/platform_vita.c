/* A one-shot resource diagnostic. Never loads modules or starts a service. */
#ifdef BD_PLATFORM_HOST
#include "test_platform.h"
#else
#include <stdint.h>
#include <stddef.h>
#include <psp2/appmgr.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#endif

#define BD_ROOT "ux0:data/vita-boot-diagnostic"
#define BD_MODE (0600|SCE_S_IRSYS|SCE_S_IWSYS)
#define BD_LOG_LIMIT 8192u
#define BD_MISSING ((int)0x80010002u)
static int submitted;
static SceUID worker_id=-1;

#ifndef BD_PLATFORM_HOST
void *memset(void *out,int value,size_t count) { return sceClibMemset(out,value,count); }
#endif
static uint64_t now_ms(void) { return sceKernelGetSystemTimeWide()/1000; }
static int exists(const char *path) {
    SceIoStat info={0};int result=sceIoGetstat(path,&info);
    return result>=0 ? 1 : result==BD_MISSING ? 0 : -1;
}
static void log_line(const char *message,int result) {
    const char *path=DIAGNOSTIC_MODULE_ROOT "startup.log";
    SceIoStat info={0};int status=sceIoGetstat(path,&info);
    if(status<0 && status!=BD_MISSING) return;
    if(status>=0 && (!SCE_S_ISREG(info.st_mode) || info.st_size<0 || info.st_size>=BD_LOG_LIMIT)) return;
    char line[224];int count=sceClibSnprintf(line,sizeof(line),"tick_ms=%llu %s result=0x%08x\n",
        (unsigned long long)now_ms(),message,(unsigned)result);
    if(count<=0 || (unsigned)count>=sizeof(line) ||
       (status>=0 && (uint64_t)info.st_size+(unsigned)count>BD_LOG_LIMIT)) return;
    int fd=sceIoOpen(path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,BD_MODE);
    if(fd>=0) { sceIoWrite(fd,line,(unsigned)count);sceIoClose(fd); }
}
static int enabled(void) {
    if(exists(BD_ROOT "/disabled")!=0) return 0;
    int fd=sceIoOpen(BD_ROOT "/enable.once",SCE_O_RDONLY,0);
    if(fd<0) return 0;
    char value[66]={0};int count=sceIoRead(fd,value,sizeof(value));unsigned char tail;
    int extra=sceIoRead(fd,&tail,1),closed=sceIoClose(fd);
    if(extra!=0 || closed<0 || (count!=64 && !(count==65 && value[64]=='\n'))) return 0;
    value[64]=0;return sceClibStrcmp(value,DIAGNOSTIC_BUILD_ID)==0;
}
static int guards_clear(void) {
    return enabled() && exists(BD_ROOT "/attempt.inflight")==0 && exists(BD_ROOT "/enable.consumed")==0;
}
static int ready(void) {
    SceInt32 apps[16]={0};
    if(sceAppMgrGetRunningAppIdListForShell(apps,16)<0) return 0;
    /* Historical versions may return status 0 rather than the item count. */
    for(unsigned i=0;i<16;i++) {
        if(apps[i]<=0) continue;
        SceUID pid=sceAppMgrGetProcessIdByAppIdForShell(apps[i]);char name[32]={0};
        if(pid>0 && sceAppMgrGetNameById(pid,name)>=0 && name[31]==0 &&
           sceClibStrcmp(name,"NPXS10079")==0) return 1;
    }
    return 0;
}
static int wait_ready(void) {
    unsigned stable=0;
    for(unsigned samples=0;samples<120;samples++) {
        if(exists(BD_ROOT "/disabled")!=0) return -1;
        if(now_ms()>=15000 && ready()) { if(++stable==3) return 0; }
        else stable=0;
        if(sceKernelDelayThread(500000)<0) return -1;
    }
    return -1;
}
static int claim(void) {
    if(!guards_clear()) return -1;
    int fd=sceIoOpen(BD_ROOT "/attempt.inflight",SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,BD_MODE);
    log_line("exclusive one-shot guard open",fd);if(fd<0) return fd;
    int written=sceIoWrite(fd,DIAGNOSTIC_BUILD_ID "\n",65);
    int synced=written==65 ? sceIoSyncByFd(fd,0) : -1;
    int closed=sceIoClose(fd);
    log_line("guard write bytes",written);log_line("guard sync",synced);log_line("guard close",closed);
    if(written!=65 || synced<0 || closed<0) return -1;
    if(exists(BD_ROOT "/enable.consumed")!=0) return -1;
    int result=sceIoRename(BD_ROOT "/enable.once",BD_ROOT "/enable.consumed");
    log_line("opt-in consumed before resource calls",result);if(result<0) return result;
    result=sceIoSync("ux0:",0);log_line("consumed opt-in storage sync",result);
    return result;
}
static int child(unsigned size,void *arg) { (void)size;(void)arg;return 0; }
static int resource_trial(void) {
    if(exists(BD_ROOT "/disabled")!=0) return -1;
    /* Addresses of our own linked import stubs, never a pointer dereference. */
    log_line("CreateMutex import address",(int)(uintptr_t)&sceKernelCreateMutex);
    log_line("CreateThread import address",(int)(uintptr_t)&sceKernelCreateThread);
    log_line("StartThread import address",(int)(uintptr_t)&sceKernelStartThread);
    SceUID mutex=sceKernelCreateMutex("boot-diag-power",0,0,0);
    log_line("CreateMutex attrs=0 count=0",mutex);if(mutex<0) return mutex;
    int result=-1;SceUID thread=-1;
    if(exists(BD_ROOT "/disabled")!=0) goto release_mutex;
    thread=sceKernelCreateThread("boot-diag-power",child,0x60,32768,0,0,0);
    log_line("CreateThread priority=0x60 stack=32768 attrs=0",thread);
    if(thread<0) { result=thread;goto release_mutex; }
    if(exists(BD_ROOT "/disabled")!=0) goto release_thread;
    result=sceKernelStartThread(thread,0,0);log_line("StartThread child",result);
    if(result<0) goto release_thread;
    SceUInt timeout=5000000;
    result=sceKernelWaitThreadEnd(thread,0,&timeout);log_line("WaitThreadEnd child bounded 5s",result);
    if(result<0) { log_line("child state unknown; owned resources retained",result);return result; }
release_thread:;
    int deleted=sceKernelDeleteThread(thread);log_line("DeleteThread owned child",deleted);
    if(deleted<0) { log_line("owned child delete unconfirmed; mutex retained",deleted);return deleted; }
release_mutex:;
    int deleted_mutex=sceKernelDeleteMutex(mutex);log_line("DeleteMutex owned resource",deleted_mutex);
    return result<0 ? result : deleted_mutex;
}
static int worker(unsigned size,void *arg) {
    (void)size;(void)arg;
    log_line("isolated boot resource diagnostic 0.1.0",0);
    log_line("source build " DIAGNOSTIC_BUILD_ID,0);
    log_line("own PID",sceKernelGetProcessId());log_line("own thread",sceKernelGetThreadId());
    if(!guards_clear()) { log_line("disabled, unarmed or stale guard; no trial",-1);return 0; }
    int result=wait_ready();log_line("minimum 15s and stable LiveArea readiness",result);
    if(result<0) return 0;
    result=claim();if(result<0) { log_line("one-shot claim failed; no trial",result);return 0; }
    result=resource_trial();log_line("resource trial completed; no service was loaded",result);
    return 0;
}
int module_start(SceSize size,const void *arg) {
    (void)size;(void)arg;
    /* The loader thread does no IO, AppMgr, networking or Control calls. */
    int expected=0;
    if(!__atomic_compare_exchange_n(&submitted,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) return SCE_KERNEL_START_FAILED;
    worker_id=sceKernelCreateThread("vita-boot-diagnostic",worker,0x40,32768,0,0,0);
    if(worker_id<0) return SCE_KERNEL_START_FAILED;
    if(sceKernelStartThread(worker_id,0,0)<0) { sceKernelDeleteThread(worker_id);worker_id=-1;return SCE_KERNEL_START_FAILED; }
    return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize size,const void *arg) {
    (void)size;(void)arg;return SCE_KERNEL_STOP_CANCEL;
}
int _start(SceSize size,const void *arg) __attribute__((weak,alias("module_start")));
