#include "autostart.h"
#include "../platform.h"
#include "../sha256.h"
#ifdef AO_PLATFORM_HOST
#include "test_vita_platform.h"
#else
#include "probe_hash.h"
#include <psp2/appmgr.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <taihen.h>
#endif

#define AO_MODE_FILE (0600|SCE_S_IRSYS|SCE_S_IWSYS)
#define AO_MODE_DIR (0700|SCE_S_IRSYS|SCE_S_IWSYS)
#define AO_LOG_LIMIT 8192u
#define AO_MODULE_LIMIT (256u*1024u)

static volatile int running,worker_submitted;
static SceUID worker_id=-1;
static RBootstrapArgs job;
static char directory[128];

/* There is no libc dependency in a SceShell user plugin. */
#ifndef AO_PLATFORM_HOST
void *memset(void *out,int value,size_t size) { return sceClibMemset(out,value,size); }
void *memcpy(void *out,const void *source,size_t size) { return sceClibMemcpy(out,source,size); }
#endif

static uint64_t now_ms(void *ctx) { (void)ctx;return sceKernelGetSystemTimeWide()/1000; }
static int exists(const char *path);
static int is_running(void *ctx) {
    (void)ctx;
    return __atomic_load_n(&running,__ATOMIC_ACQUIRE) && exists(AO_ROOT "/disabled")==0;
}
static void delay_ms(void *ctx,unsigned value) { (void)ctx;sceKernelDelayThread(value*1000); }

static int exists(const char *path) {
    SceIoStat info={0};int result=sceIoGetstat(path,&info);
    return result>=0 ? 1 : result==(int)0x80010002u ? 0 : -1;
}
static void log_line(const char *message,int result) {
    SceIoStat info={0};int got=sceIoGetstat(AO_ROOT "/startup.log",&info);
    if(got<0 && got!=(int)0x80010002u) return;
    if(got>=0 && (info.st_size<0 || info.st_size>=AO_LOG_LIMIT)) return;
    char line[224];
    int count=sceClibSnprintf(line,sizeof(line),"tick_ms=%llu %s result=0x%08x\n",
        (unsigned long long)now_ms(0),message,(unsigned)result);
    if(count<=0 || (unsigned)count>=sizeof(line) ||
       (got>=0 && (uint64_t)info.st_size+(unsigned)count>AO_LOG_LIMIT)) return;
    int fd=sceIoOpen(AO_ROOT "/startup.log",SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,AO_MODE_FILE);
    if(fd>=0) { sceIoWrite(fd,line,(unsigned)count);sceIoClose(fd); }
}
static void event(void *ctx,AOState state,int result) { (void)ctx;log_line(ao_state_name(state),result); }

static int armed(void *ctx) {
    (void)ctx;
    int disabled=exists(AO_ROOT "/disabled");
    if(disabled!=0) return disabled>0 ? 0 : -1;
    int fd=sceIoOpen(AO_ROOT "/enable.once",SCE_O_RDONLY,0);
    if(fd<0) return fd==(int)0x80010002u ? 0 : fd;
    char value[66]={0};int count=sceIoRead(fd,value,sizeof(value));
    unsigned char tail;int extra=sceIoRead(fd,&tail,1);
    int closed=sceIoClose(fd);
    if(closed<0 || extra!=0 || (count!=64 && !(count==65 && value[64]=='\n'))) return -1;
    value[64]=0;
    return sceClibStrcmp(value,CONTROL_BUILD_ID) ? -1 : 1;
}

static int guards_clear(void *ctx) {
    if(armed(ctx)!=1) return -1;
    if(exists(AO_ROOT "/attempt.inflight")!=0 ||
       exists(AO_ROOT "/enable.consumed")!=0 || exists(RC_BOOT_GUARD)!=0) return -1;
    return 1;
}

static int readiness(void *ctx) {
    (void)ctx;
    SceInt32 apps[16]={0};
    int count=sceAppMgrGetRunningAppIdListForShell(apps,16);
    if(count<0) return 0;
    /* Some historical AppMgr versions return status rather than a count. */
    for(unsigned index=0;index<16;index++) {
        if(apps[index]<=0) continue;
        SceUID pid=sceAppMgrGetProcessIdByAppIdForShell(apps[index]);
        if(pid<=0) continue;
        char name[32]={0};
        if(sceAppMgrGetNameById(pid,name)>=0 && name[31]==0 &&
           !sceClibStrcmp(name,"NPXS10079")) return 1;
    }
    return 0;
}

static int write_exclusive(const char *path,const void *bytes,unsigned length) {
    int fd=sceIoOpen(path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,AO_MODE_FILE);
    if(fd<0) return fd;
    int written=sceIoWrite(fd,bytes,length);
    int synced=written==(int)length ? sceIoSyncByFd(fd,0) : -1;
    int closed=sceIoClose(fd);
    return written==(int)length && synced>=0 && closed>=0 ? 0 : -1;
}

static int claim(void *ctx) {
    if(guards_clear(ctx)!=1) return -1;
    job.magic=RC_BOOT_ARGS_MAGIC;job.mode=1;
    sceClibSnprintf(job.run,sizeof(job.run),"%016llx%08x%08x",
        (unsigned long long)sceKernelGetSystemTimeWide(),(unsigned)sceKernelGetProcessId(),1u);
    sceClibSnprintf(directory,sizeof(directory),AO_ROOT "/%s",job.run);
    int result=sceIoMkdir(directory,AO_MODE_DIR);
    log_line("unique report directory",result);
    if(result<0) return result;
    result=write_exclusive(AO_ROOT "/attempt.inflight",&job,sizeof(job));
    log_line("exclusive in-flight guard",result);
    if(result<0) return result;
    /* Consuming the sole opt-in precedes every native module submission. */
    if(exists(AO_ROOT "/enable.consumed")!=0) return -1;
    result=sceIoRename(AO_ROOT "/enable.once",AO_ROOT "/enable.consumed");
    log_line("one-shot opt-in consumed",result);
    if(result<0) return result;
    result=sceIoSync("ux0:",0);
    log_line("consumed opt-in storage sync",result);
    if(result<0) return result;
    result=write_exclusive(RC_BOOT_GUARD,&job,sizeof(job));
    log_line("legacy Starter guard retained",result);
    return result;
}

static int hash_matches(const char *path,const char *expected) {
    SceIoStat info={0};int result=sceIoGetstat(path,&info);
    if(result<0 || !SCE_S_ISREG(info.st_mode) || info.st_size<=0 || info.st_size>AO_MODULE_LIMIT) return -1;
    int fd=sceIoOpen(path,SCE_O_RDONLY,0);if(fd<0) return fd;
    RSha sha;rs_init(&sha);unsigned char chunk[4096];uint64_t total=0;
    while(total<(uint64_t)info.st_size) {
        unsigned wanted=(uint64_t)info.st_size-total>sizeof(chunk) ? sizeof(chunk) : (unsigned)((uint64_t)info.st_size-total);
        int count=sceIoRead(fd,chunk,wanted);
        if(count<=0 || (unsigned)count>wanted) { sceIoClose(fd);return -1; }
        total+=(unsigned)count;rs_update(&sha,chunk,(unsigned)count);
    }
    unsigned char tail;int extra=sceIoRead(fd,&tail,1),closed=sceIoClose(fd);
    char actual[65];rs_final(&sha,actual);
    return extra==0 && closed>=0 && !sceClibStrcmp(actual,expected) ? 0 : -1;
}
static int verify_files(void *ctx) {
    (void)ctx;
    int result=hash_matches(CONTROL_MODULE_ROOT "vita_control_kernel.skprx",CONTROL_KERNEL_SHA256);
    log_line("kernel file SHA-256",result);if(result<0) return result;
    result=hash_matches(CONTROL_MODULE_ROOT "vita_control.suprx",CONTROL_SERVICE_SHA256);
    log_line("service file SHA-256",result);if(result<0) return result;
    result=hash_matches(CONTROL_MODULE_ROOT "autostart_shell_probe.suprx",AO_PROBE_SHA256);
    log_line("Shell probe file SHA-256",result);return result;
}
static int load_kernel(void *ctx) {
    (void)ctx;tai_module_args_t args={0};args.size=sizeof(args);args.pid=KERNEL_PID;
    log_line("submitting kernel exactly once",0);
    int result=taiLoadStartKernelModuleForUser(CONTROL_MODULE_ROOT "vita_control_kernel.skprx",&args);
    log_line("kernel loader receipt",result);return result;
}
static AOProbe load_probe(void *ctx) {
    (void)ctx;AOProbe out={.module_id=-1,.start_result=-1,.metadata_result=-1};
    out.module_id=sceKernelLoadStartModule(CONTROL_MODULE_ROOT "autostart_shell_probe.suprx",sizeof(job),&job,0,0,&out.start_result);
    log_line("Shell probe loader receipt",out.module_id);log_line("Shell probe module_start",out.start_result);
    if(out.module_id<0) return out;
    char path[160];sceClibSnprintf(path,sizeof(path),"%s/bootstrap.bin",directory);
    int fd=sceIoOpen(path,SCE_O_RDONLY,0);
    log_line("Shell metadata file open",fd);
    if(fd>=0) {
        int count=sceIoRead(fd,&out.info,sizeof(out.info));unsigned char tail;
        int extra=count==(int)sizeof(out.info) ? sceIoRead(fd,&tail,1) : -1;
        int closed=sceIoClose(fd);
        log_line("Shell metadata bytes read",count);
        log_line("Shell metadata EOF read",extra);
        log_line("Shell metadata file close",closed);
        if(count==(int)sizeof(out.info) && extra==0 && closed>=0) out.metadata_result=0;
    }
    log_line("Shell metadata read",out.metadata_result);
    if(out.metadata_result==0) {
        log_line("metadata caller before",out.info.caller_before);
        log_line("metadata caller after",out.info.caller_after);
        log_line("metadata Shell PID",out.info.shell_pid);
        log_line("metadata Shell guard allowed",out.info.guard_allowed);
        log_line("metadata readiness",out.info.ready);
    }
    return out;
}
static int release_probe(void *ctx,int module) {
    (void)ctx;int status=-1;
    int result=sceKernelStopUnloadModule(module,0,0,0,0,&status);
    log_line("temporary probe stop/unload",result);log_line("temporary probe module_stop",status);
    return result>=0 && status==SCE_KERNEL_STOP_SUCCESS ? 0 : result<0 ? result : -1;
}
static int load_service(void *ctx,int *status) {
    (void)ctx;log_line("submitting own-Shell service exactly once",0);
    int result=sceKernelLoadStartModule(CONTROL_MODULE_ROOT "vita_control.suprx",0,0,0,0,status);
    log_line("Shell service loader receipt",result);log_line("Shell service module_start",*status);
    return result;
}
static const AOPlatform platform={now_ms,is_running,delay_ms,armed,readiness,guards_clear,claim,
    verify_files,load_kernel,load_probe,release_probe,load_service,event};
static int worker(unsigned size,void *arg) {
    (void)size;(void)arg;
    log_line("experimental one-shot autostart 0.1.0 worker",0);
    log_line("worker own PID",sceKernelGetProcessId());
    AOResult result=ao_run(&platform,0,sceKernelGetProcessId(),CONTROL_BUILD_ID);
    log_line("completed state",result.state);
    log_line("network acceptance remains external",result.network_verified);
    return 0;
}

int module_start(SceSize size,const void *arg) {
    (void)size;(void)arg;
    /* No IO, networking, AppMgr, or Control calls on taiHEN's loader thread. */
    int expected=0;
    if(!__atomic_compare_exchange_n(&worker_submitted,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
        return SCE_KERNEL_START_FAILED;
    __atomic_store_n(&running,1,__ATOMIC_RELEASE);
    worker_id=sceKernelCreateThread("vita-autostart",worker,0x40,32*1024,0,0,0);
    if(worker_id<0) return SCE_KERNEL_START_FAILED;
    if(sceKernelStartThread(worker_id,0,0)<0) {
        sceKernelDeleteThread(worker_id);worker_id=-1;return SCE_KERNEL_START_FAILED;
    }
    return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize size,const void *arg) {
    (void)size;(void)arg;
    /* Loaded native modules, any in-flight syscall and this worker stay resident. */
    return SCE_KERNEL_STOP_CANCEL;
}
int _start(SceSize size,const void *arg) __attribute__((weak,alias("module_start")));
