#define BD_PLATFORM_HOST
#define DIAGNOSTIC_BUILD_ID "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
#define DIAGNOSTIC_MODULE_ROOT "ux0:data/vita-boot-diagnostic/setup-01234567-89ab-cdef/"
#include <assert.h>
#include <stdlib.h>
#include "platform_vita.c"

enum { ENABLE,DISABLED,GUARD,CONSUMED,LOG,FILES };
static const char *const paths[FILES]={BD_ROOT "/enable.once",BD_ROOT "/disabled",BD_ROOT "/attempt.inflight",BD_ROOT "/enable.consumed",DIAGNOSTIC_MODULE_ROOT "startup.log"};
typedef struct { int present;unsigned length,position,mode;char bytes[BD_LOG_LIMIT+1]; } File;
static File files[FILES];
static uint64_t clock_us;
static int ready_mode,ready_calls,delay_calls,io_calls,stat_bad=-1;
static int guard_open_error,guard_write_short,guard_sync_error,guard_close_error,enable_close_error,rename_error,sync_error,sync_done;
static int mutex_error,thread_error,start_error,wait_error,delete_thread_error,delete_mutex_error,worker_create_error,worker_start_error;
static int cancel_after_mutex,cancel_after_thread,mutex_calls,thread_calls,start_calls,wait_calls,delete_thread_calls,delete_mutex_calls;
static int worker_create_calls,worker_start_calls,worker_delete_calls;
static int (*child_entry)(unsigned,void *);
static int slot(const char *path) {
    for(int i=0;i<FILES;i++) if(strcmp(path,paths[i])==0) return i;
    assert(!"unexpected file path; diagnostic escaped its private namespace");return -1;
}
static void put(int i,const char *bytes,unsigned count) {
    assert(count<=BD_LOG_LIMIT);files[i].present=1;files[i].length=count;
    memcpy(files[i].bytes,bytes,count);files[i].bytes[count]=0;
}
static void reset(void) {
    memset(files,0,sizeof(files));put(ENABLE,DIAGNOSTIC_BUILD_ID "\n",65);
    clock_us=0;ready_mode=0;ready_calls=delay_calls=io_calls=0;stat_bad=-1;
    guard_open_error=guard_write_short=guard_sync_error=guard_close_error=enable_close_error=rename_error=sync_error=sync_done=0;
    mutex_error=thread_error=start_error=wait_error=delete_thread_error=delete_mutex_error=worker_create_error=worker_start_error=0;
    cancel_after_mutex=cancel_after_thread=mutex_calls=thread_calls=start_calls=wait_calls=delete_thread_calls=delete_mutex_calls=0;
    worker_create_calls=worker_start_calls=worker_delete_calls=0;child_entry=0;submitted=0;worker_id=-1;
}
uint64_t sceKernelGetSystemTimeWide(void) { return clock_us; }
int sceKernelGetProcessId(void) { return 0x1188d; }
int sceKernelGetThreadId(void) { return 0x11223; }
int sceKernelDelayThread(unsigned micros) { assert(micros==500000);clock_us+=micros;++delay_calls;return 0; }
int sceIoGetstat(const char *path,SceIoStat *out) {
    ++io_calls;int i=slot(path);if(i==stat_bad) return -99;
    if(!files[i].present) return BD_MISSING;
    out->st_size=files[i].length;out->st_mode=0x8000;return 0;
}
int sceIoOpen(const char *path,int flags,int mode) {
    ++io_calls;int i=slot(path);File *f=&files[i];
    if(i==GUARD && guard_open_error) return -21;
    if((flags&SCE_O_EXCL) && f->present) return -22;
    if(!f->present && !(flags&SCE_O_CREAT)) return BD_MISSING;
    if(flags&SCE_O_CREAT) { assert(mode==BD_MODE);f->present=1; }
    f->mode=(unsigned)flags;f->position=flags&SCE_O_APPEND ? f->length : 0;
    return i+1;
}
int sceIoRead(int fd,void *out,unsigned size) {
    ++io_calls;assert(fd>0 && fd<=FILES);File *f=&files[fd-1];
    assert(f->mode==SCE_O_RDONLY);unsigned count=f->length-f->position;if(count>size)count=size;
    memcpy(out,f->bytes+f->position,count);f->position+=count;return (int)count;
}
int sceIoWrite(int fd,const void *bytes,unsigned size) {
    ++io_calls;assert(fd>0 && fd<=FILES);int i=fd-1;File *f=&files[i];
    assert(f->mode&SCE_O_WRONLY);if(i==GUARD && guard_write_short) size--;
    assert(f->position+size<=BD_LOG_LIMIT);memcpy(f->bytes+f->position,bytes,size);f->position+=size;
    if(f->position>f->length)f->length=f->position;
    f->bytes[f->length]=0;return (int)size;
}
int sceIoClose(int fd) { ++io_calls;return fd==GUARD+1 && guard_close_error ? -23 : fd==ENABLE+1 && enable_close_error ? -24 : 0; }
int sceIoRename(const char *old_path,const char *new_path) {
    ++io_calls;assert(slot(old_path)==ENABLE && slot(new_path)==CONSUMED);
    assert(files[GUARD].present && !files[CONSUMED].present);if(rename_error)return -25;
    files[CONSUMED]=files[ENABLE];files[ENABLE].present=0;return 0;
}
int sceIoSyncByFd(int fd,int flags) { ++io_calls;assert(fd==GUARD+1 && flags==0);return guard_sync_error ? -26 : 0; }
int sceIoSync(const char *device,int flags) {
    ++io_calls;assert(!strcmp(device,"ux0:") && flags==0);if(sync_error)return -27;sync_done=1;return 0;
}
int sceAppMgrGetRunningAppIdListForShell(int *apps,int capacity) {
    assert(capacity==16);++ready_calls;assert(clock_us>=15000000);
    if(ready_mode==1)return -28;
    if(ready_mode==2)return 0;
    if(ready_mode==3 && ready_calls%3==0)return 0;
    apps[15]=23;return 0; /* Verify success-status API and the final initialized slot. */
}
int sceAppMgrGetProcessIdByAppIdForShell(int app) { assert(app==23);return 123; }
int sceAppMgrGetNameById(int pid,char *name) { assert(pid==123);strcpy(name,ready_mode==4 ? "OTHER" : "NPXS10079");return 0; }
int sceKernelCreateMutex(const char *name,int attrs,int count,void *options) {
    assert(!strcmp(name,"boot-diag-power") && attrs==0 && count==0 && !options);
    assert(files[CONSUMED].present && !files[ENABLE].present && files[GUARD].length==65 && sync_done);
    ++mutex_calls;if(cancel_after_mutex)put(DISABLED,"",0);return mutex_error ? -101 : 30;
}
int sceKernelDeleteMutex(int mutex) { assert(mutex==30);++delete_mutex_calls;return delete_mutex_error ? -106 : 0; }
int sceKernelCreateThread(const char *name,int (*entry)(unsigned,void *),int priority,unsigned stack,int flags,int affinity,void *options) {
    assert(stack==32768 && flags==0 && affinity==0 && !options);
    if(!strcmp(name,"vita-boot-diagnostic")) { assert(priority==0x40 && entry==worker);++worker_create_calls;return worker_create_error ? -111 : 10; }
    assert(!strcmp(name,"boot-diag-power") && priority==0x60 && entry==child);
    ++thread_calls;child_entry=entry;if(cancel_after_thread)put(DISABLED,"",0);return thread_error ? -102 : 20;
}
int sceKernelStartThread(int thread,unsigned size,void *arg) {
    assert(!size && !arg);
    if(thread==10) { ++worker_start_calls;return worker_start_error ? -112 : 0; }
    assert(thread==20);++start_calls;if(start_error)return -103;assert(child_entry(0,0)==0);return 0;
}
int sceKernelWaitThreadEnd(int thread,int *status,SceUInt *timeout) {
    assert(thread==20 && !status && *timeout==5000000);++wait_calls;return wait_error ? -104 : 0;
}
int sceKernelDeleteThread(int thread) {
    if(thread==10) { ++worker_delete_calls;return 0; }
    assert(thread==20);++delete_thread_calls;return delete_thread_error ? -105 : 0;
}
static void run(void) { assert(worker(0,0)==0);assert(files[LOG].length<=BD_LOG_LIMIT); }
static void no_trial(void) { assert(!mutex_calls && !thread_calls && !start_calls && !wait_calls && !delete_mutex_calls && !delete_thread_calls); }
static void logged(const char *text) { assert(strstr(files[LOG].bytes,text)); }
int main(void) {
    unsigned cases=0;
    reset();run();assert(mutex_calls==1 && thread_calls==1 && start_calls==1 && wait_calls==1 && delete_thread_calls==1 && delete_mutex_calls==1);
    assert(clock_us==16000000 && ready_calls==3 && !files[ENABLE].present);logged("resource trial completed; no service was loaded result=0x00000000");++cases;
    reset();run();int calls=mutex_calls;run();assert(mutex_calls==calls);++cases;
    reset();files[ENABLE].present=0;run();no_trial();assert(!delay_calls);++cases;
    reset();put(DISABLED,"",0);run();no_trial();++cases;
    reset();files[ENABLE].bytes[0]='f';run();no_trial();++cases;
    reset();put(ENABLE,DIAGNOSTIC_BUILD_ID "xx",66);run();no_trial();++cases;
    reset();put(ENABLE,DIAGNOSTIC_BUILD_ID,64);run();assert(mutex_calls==1);++cases;
    reset();enable_close_error=1;run();no_trial();++cases;
    reset();stat_bad=DISABLED;run();no_trial();++cases;
    reset();put(GUARD,"old",3);run();no_trial();assert(!delay_calls);++cases;
    reset();put(CONSUMED,"old",3);run();no_trial();++cases;
    reset();ready_mode=1;run();no_trial();assert(delay_calls==120 && clock_us==60000000);++cases;
    reset();ready_mode=2;run();no_trial();++cases;
    reset();ready_mode=3;run();no_trial();++cases;
    reset();ready_mode=4;run();no_trial();++cases;
    reset();clock_us=200000000;run();assert(mutex_calls==1 && delay_calls==2);++cases;
    reset();guard_open_error=1;run();no_trial();assert(files[ENABLE].present);++cases;
    reset();guard_write_short=1;run();no_trial();assert(files[GUARD].present && files[ENABLE].present);++cases;
    reset();guard_sync_error=1;run();no_trial();++cases;
    reset();guard_close_error=1;run();no_trial();++cases;
    reset();rename_error=1;run();no_trial();assert(files[GUARD].present && files[ENABLE].present);++cases;
    reset();sync_error=1;run();no_trial();assert(files[CONSUMED].present && !files[ENABLE].present);++cases;
    reset();mutex_error=1;run();assert(mutex_calls==1 && !thread_calls && !delete_mutex_calls);logged("CreateMutex attrs=0 count=0 result=0xffffff9b");++cases;
    reset();thread_error=1;run();assert(thread_calls==1 && !start_calls && !delete_thread_calls && delete_mutex_calls==1);logged("CreateThread priority=0x60 stack=32768 attrs=0 result=0xffffff9a");++cases;
    reset();start_error=1;run();assert(start_calls==1 && !wait_calls && delete_thread_calls==1 && delete_mutex_calls==1);logged("StartThread child result=0xffffff99");++cases;
    reset();wait_error=1;run();assert(wait_calls==1 && !delete_thread_calls && !delete_mutex_calls);logged("child state unknown; owned resources retained");++cases;
    reset();delete_thread_error=1;run();assert(delete_thread_calls==1 && !delete_mutex_calls);++cases;
    reset();delete_mutex_error=1;run();assert(delete_mutex_calls==1);logged("DeleteMutex owned resource result=0xffffff96");++cases;
    reset();cancel_after_mutex=1;run();assert(mutex_calls==1 && !thread_calls && delete_mutex_calls==1);++cases;
    reset();cancel_after_thread=1;run();assert(thread_calls==1 && !start_calls && delete_thread_calls==1 && delete_mutex_calls==1);++cases;
    reset();put(LOG,"",0);files[LOG].length=BD_LOG_LIMIT-1;run();assert(files[LOG].length==BD_LOG_LIMIT-1 && mutex_calls==1);++cases;
    reset();assert(module_start(0,0)==SCE_KERNEL_START_SUCCESS);assert(!io_calls && !delay_calls && worker_create_calls==1 && worker_start_calls==1);
    assert(module_start(0,0)==SCE_KERNEL_START_FAILED && worker_create_calls==1);assert(module_stop(0,0)==SCE_KERNEL_STOP_CANCEL);++cases;
    reset();worker_create_error=1;assert(module_start(0,0)==SCE_KERNEL_START_FAILED && !io_calls && !worker_start_calls && !worker_delete_calls);++cases;
    reset();worker_start_error=1;assert(module_start(0,0)==SCE_KERNEL_START_FAILED && !io_calls && worker_delete_calls==1);++cases;
    printf("PASS boot diagnostic actual-adapter tests: %u cases\n",cases);return 0;
}
