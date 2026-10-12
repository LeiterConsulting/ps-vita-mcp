/* Compile the actual adapter, including module_start and marker operations. */
#define AO_PLATFORM_HOST
#define CONTROL_BUILD_ID "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
#define CONTROL_MODULE_ROOT "ux0:data/vita-autostart/setup-0123456789abcdef/"
#define CONTROL_KERNEL_SHA256 "6923dd1bc0460082c5d55a831908c24a282860b7f1cd6c2b79cf1bc8857c639c"
#define CONTROL_SERVICE_SHA256 "9df6b026a8c6c26e3c3acd2370a16e93fffdc0015ff5bd879218788025db0280"
#include "platform_vita.c"
#include <assert.h>

typedef struct { char path[192];unsigned char bytes[8192];unsigned size,pos,mode;int exists; } File;
static File files[64];
static uint64_t clock_ms;
static int io_calls,kernel_calls,probe_calls,service_calls,unloads,thread_creates,thread_starts,thread_deletes;
static int start_failure,create_failure,rename_failure,sync_failure,short_guard_write,app_status,app_ready;
static int disable_on_kernel,disable_on_probe,kernel_error,probe_error,service_error;
static int (*entry_point)(unsigned,void *);
static int find(const char *path) { for(unsigned i=0;i<64;i++)if(files[i].exists && !strcmp(path,files[i].path))return (int)i;return -1; }
static int put(const char *path,const void *bytes,unsigned size,unsigned mode) {
    int slot=find(path);
    if(slot<0)for(unsigned i=0;i<64;i++)if(!files[i].exists){slot=(int)i;break;}
    assert(slot>=0 && size<=sizeof(files[slot].bytes));
    snprintf(files[slot].path,sizeof(files[slot].path),"%s",path);files[slot].exists=1;
    files[slot].size=size;files[slot].pos=0;files[slot].mode=mode;
    if(size)memcpy(files[slot].bytes,bytes,size);
    return slot;
}
static void reset(void) {
    memset(files,0,sizeof(files));memset(&job,0,sizeof(job));directory[0]=0;
    running=worker_submitted=0;worker_id=-1;clock_ms=0;
    io_calls=kernel_calls=probe_calls=service_calls=unloads=thread_creates=thread_starts=thread_deletes=0;
    start_failure=create_failure=rename_failure=sync_failure=short_guard_write=0;
    disable_on_kernel=disable_on_probe=kernel_error=probe_error=service_error=0;
    app_status=0;app_ready=1;entry_point=0;
    put(AO_ROOT,0,0,0x4000);put(RC_BOOT_ROOT,0,0,0x4000);
    put(AO_ROOT "/enable.once",CONTROL_BUILD_ID,64,0x8000);
    put(CONTROL_MODULE_ROOT "vita_control_kernel.skprx","kernel",6,0x8000);
    put(CONTROL_MODULE_ROOT "vita_control.suprx","service",7,0x8000);
    put(CONTROL_MODULE_ROOT "autostart_shell_probe.suprx","probe",5,0x8000);
}
uint64_t sceKernelGetSystemTimeWide(void) { return clock_ms*1000; }
int sceKernelGetProcessId(void) { return 84; }
int sceKernelDelayThread(unsigned micros) { clock_ms+=micros/1000;return 0; }
int sceIoGetstat(const char *path,SceIoStat *out) { io_calls++;int id=find(path);if(id<0)return (int)0x80010002u;out->st_size=files[id].size;out->st_mode=files[id].mode;return 0; }
int sceIoOpen(const char *path,int flags,int mode) {
    io_calls++;int id=find(path);
    if((flags&SCE_O_EXCL) && id>=0)return -2;
    if(id<0 && (flags&SCE_O_CREAT))id=put(path,0,0,0x8000|(unsigned)mode);
    if(id<0)return (int)0x80010002u;
    files[id].pos=(flags&SCE_O_APPEND) ? files[id].size : 0;return id+1;
}
int sceIoRead(int fd,void *out,unsigned size) { io_calls++;File *f=&files[fd-1];unsigned count=f->size-f->pos;if(count>size)count=size;memcpy(out,f->bytes+f->pos,count);f->pos+=count;return (int)count; }
int sceIoWrite(int fd,const void *bytes,unsigned size) {
    io_calls++;File *f=&files[fd-1];assert(f->pos+size<=sizeof(f->bytes));
    if(short_guard_write && !strcmp(f->path,AO_ROOT "/attempt.inflight"))size--;
    memcpy(f->bytes+f->pos,bytes,size);f->pos+=size;if(f->size<f->pos)f->size=f->pos;return (int)size;
}
int sceIoClose(int fd) { io_calls++;assert(fd>0);return 0; }
int sceIoRename(const char *old_path,const char *new_path) {
    io_calls++;int id=find(old_path);if(rename_failure || id<0 || find(new_path)>=0)return -3;
    snprintf(files[id].path,sizeof(files[id].path),"%s",new_path);return 0;
}
int sceIoSyncByFd(int fd,int flags) { io_calls++;assert(fd>0 && !flags);return sync_failure ? -4 : 0; }
int sceIoSync(const char *device,int flags) { io_calls++;assert(!strcmp(device,"ux0:") && !flags);return sync_failure ? -4 : 0; }
int sceIoMkdir(const char *path,int mode) { io_calls++;if(find(path)>=0)return -1;put(path,0,0,0x4000|(unsigned)mode);return 0; }
int sceAppMgrGetRunningAppIdListForShell(int *apps,int capacity) { assert(capacity==16);if(app_ready)apps[15]=101;return app_status; }
int sceAppMgrGetProcessIdByAppIdForShell(int app) { assert(app==101);return 111; }
int sceAppMgrGetNameById(int pid,char *name) { assert(pid==111);snprintf(name,32,"NPXS10079");return 0; }
static void assert_consumed(void) {
    assert(find(AO_ROOT "/enable.once")<0 && find(AO_ROOT "/enable.consumed")>=0 &&
           find(AO_ROOT "/attempt.inflight")>=0 && find(RC_BOOT_GUARD)>=0 && clock_ms>=16000);
}
int taiLoadStartKernelModuleForUser(const char *path,tai_module_args_t *args) {
    assert_consumed();assert(!strcmp(path,CONTROL_MODULE_ROOT "vita_control_kernel.skprx") && args->pid==KERNEL_PID && !args->args);
    kernel_calls++;assert(kernel_calls==1);
    if(disable_on_kernel)put(AO_ROOT "/disabled",0,0,0x8000);
    return kernel_error ? -5 : 41;
}
int sceKernelLoadStartModule(const char *path,unsigned size,const void *args,int flags,void *options,int *status) {
    assert_consumed();assert(!flags && !options);*status=0;
    if(!strcmp(path,CONTROL_MODULE_ROOT "autostart_shell_probe.suprx")) {
        probe_calls++;assert(probe_calls==1 && size==44 && args==&job);
        if(probe_error)return -6;
        RBootstrapInfo info={.magic=RC_BOOT_MAGIC,.abi=RC_ABI,.size=112,.ready=1,.caller_before=84,.caller_after=84,.shell_pid=84,.guard_allowed=1};
        memcpy(info.build_id,CONTROL_BUILD_ID,65);
        char path_out[160];snprintf(path_out,sizeof(path_out),"%s/bootstrap.bin",directory);
        put(path_out,&info,sizeof(info),0x8000);
        if(disable_on_probe)put(AO_ROOT "/disabled",0,0,0x8000);
        return 42;
    }
    assert(!strcmp(path,CONTROL_MODULE_ROOT "vita_control.suprx") && !size && !args);
    service_calls++;assert(service_calls==1);return service_error ? -7 : 43;
}
int sceKernelStopUnloadModule(int module,unsigned size,const void *args,int flags,void *options,int *status) {
    assert(module==42 && !size && !args && !flags && !options);unloads++;*status=0;return 0;
}
int sceKernelCreateThread(const char *name,int (*entry)(unsigned,void *),int priority,unsigned stack,int flags,int affinity,void *options) {
    assert(!strcmp(name,"vita-autostart") && priority==0x40 && stack==32768 && !flags && !affinity && !options);
    thread_creates++;entry_point=entry;return create_failure ? -1 : 123;
}
int sceKernelStartThread(int thread,unsigned size,void *arg) { assert(thread==123 && !size && !arg);thread_starts++;return start_failure ? -1 : 0; }
int sceKernelDeleteThread(int thread) { assert(thread==123);thread_deletes++;return 0; }
static void launch_worker(void) {
    assert(module_start(0,0)==0 && !io_calls && !kernel_calls && !probe_calls && !service_calls);
    assert(entry_point && thread_creates==1 && thread_starts==1);
    assert(entry_point(0,0)==0);
}
int main(void) {
    reset();launch_worker();assert(kernel_calls==1 && probe_calls==1 && service_calls==1 && unloads==1);
    int old_io=io_calls;assert(module_start(0,0)==SCE_KERNEL_START_FAILED && io_calls==old_io && thread_creates==1);
    assert(module_stop(0,0)==SCE_KERNEL_STOP_CANCEL && io_calls==old_io && unloads==1);
    reset();create_failure=1;assert(module_start(0,0)==SCE_KERNEL_START_FAILED && !io_calls && !thread_starts);
    reset();start_failure=1;assert(module_start(0,0)==SCE_KERNEL_START_FAILED && !io_calls && thread_deletes==1);
    reset();files[find(AO_ROOT "/enable.once")].exists=0;launch_worker();assert(!kernel_calls && !probe_calls);
    reset();put(AO_ROOT "/disabled",0,0,0x8000);launch_worker();assert(!kernel_calls && !probe_calls);
    reset();put(AO_ROOT "/attempt.inflight","old",3,0x8000);launch_worker();assert(!kernel_calls);
    reset();put(AO_ROOT "/enable.consumed","old",3,0x8000);launch_worker();assert(!kernel_calls);
    reset();put(RC_BOOT_GUARD,"old",3,0x8000);launch_worker();assert(!kernel_calls && find(AO_ROOT "/enable.once")>=0);
    reset();files[find(AO_ROOT "/enable.once")].bytes[0]='f';launch_worker();assert(!kernel_calls);
    reset();rename_failure=1;launch_worker();assert(!kernel_calls && find(AO_ROOT "/attempt.inflight")>=0);
    reset();sync_failure=1;launch_worker();assert(!kernel_calls && find(AO_ROOT "/attempt.inflight")>=0);
    reset();short_guard_write=1;launch_worker();assert(!kernel_calls);
    reset();files[find(CONTROL_MODULE_ROOT "vita_control_kernel.skprx")].bytes[0]='x';launch_worker();assert(!kernel_calls);
    reset();files[find(CONTROL_MODULE_ROOT "vita_control.suprx")].bytes[0]='x';launch_worker();assert(!kernel_calls);
    reset();files[find(CONTROL_MODULE_ROOT "autostart_shell_probe.suprx")].bytes[0]='x';launch_worker();assert(!kernel_calls);
    reset();app_ready=0;launch_worker();assert(!kernel_calls && clock_ms==120000);
    reset();app_status=1;launch_worker();assert(kernel_calls==1 && service_calls==1);
    reset();app_status=-1;launch_worker();assert(!kernel_calls && clock_ms==120000);
    reset();disable_on_kernel=1;launch_worker();assert(kernel_calls==1 && !probe_calls && !service_calls && !unloads);
    reset();disable_on_probe=1;launch_worker();assert(kernel_calls==1 && probe_calls==1 && unloads==1 && !service_calls);
    reset();kernel_error=1;launch_worker();assert(kernel_calls==1 && !probe_calls && !service_calls);
    reset();probe_error=1;launch_worker();assert(kernel_calls==1 && probe_calls==1 && !unloads && !service_calls);
    reset();service_error=1;launch_worker();assert(kernel_calls==1 && probe_calls==1 && unloads==1 && service_calls==1);
    puts("PASS: actual platform module_start, claim, all file hashes, readiness variants and late cancellation; 24 fixture cases, SDK simulated.");
    return 0;
}
