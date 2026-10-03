#include "api.h"
#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <vita2d.h>
#include <taihen.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#define ROOT "ux0:data/vita-control-inspector"
#define MODULE_ROOT "ux0:app/CHRS00010/"
#define SESSION_LOCK VI_SESSION_PATH
#define COLOR(r,g,b) ((unsigned)(r)|((unsigned)(g)<<8)|((unsigned)(b)<<16)|0xff000000u)
typedef struct { int available,valid; unsigned user,caller,shell,guard,info_result,build_result,guard_result; } Result;
static vita2d_pgf *font;
static VIArgs job;
static Result self_result,shell_result;
static SceUID thread=-1;
static SceUID kernel=-1;
static volatile int busy,phase;
static int cleanup_ok=1,storage_ok,previous_session;
static unsigned log_bytes,run_counter;
static char run_directory[128],journal_path[160];

static void journal(const char *message,int result) {
    if(__atomic_load_n(&log_bytes,__ATOMIC_RELAXED)>=6144) return;
    char text[160]; int n=snprintf(text,sizeof(text),"tick_us=%llu stage=%s result=0x%08x\n",(unsigned long long)sceKernelGetProcessTimeWide(),message,(unsigned)result);
    if(n<=0 || (unsigned)n>=sizeof(text)) return;
    int fd=sceIoOpen(journal_path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(fd>=0) { int written=sceIoWrite(fd,text,n); sceIoClose(fd); if(written>0) __atomic_fetch_add(&log_bytes,(unsigned)written,__ATOMIC_RELAXED); }
}
static int field(const char *text,const char *name,unsigned *value,int hex) {
    char key[48]; snprintf(key,sizeof(key),"\n%s=",name);
    const char *found=strstr(text,key); if(!found) return 0;
    return sscanf(found+strlen(key),hex?"0x%x":"%u",value)==1;
}
static Result report(unsigned mode) {
    Result r={0}; char path[160],text[1601];
    snprintf(path,sizeof(path),"%s/%s.log",run_directory,mode==1?"self":"shell");
    int fd=sceIoOpen(path,SCE_O_RDONLY,0); if(fd<0) { journal("report open",fd); return r; }
    int n=sceIoRead(fd,text,sizeof(text)-1); sceIoClose(fd);
    if(n<1 || n==(int)sizeof(text)-1) { journal("report size invalid",n); return r; }
    text[n]=0; r.available=1;
    unsigned abi=0,magic=0,size=0,matched=0,guard_matched=0,invalid=0;
    int parsed=field(text,"abi",&abi,0) && field(text,"info_result",&r.info_result,1) &&
        field(text,"info_magic",&magic,1) && field(text,"info_size",&size,0) &&
        field(text,"user_pid",&r.user,1) && field(text,"caller_after",&r.caller,1) &&
        field(text,"shell_pid",&r.shell,1) && field(text,"guard_allowed",&r.guard,0) &&
        field(text,"build_result",&r.build_result,1) && field(text,"build_matched",&matched,0) &&
        field(text,"guard_result",&r.guard_result,1) && field(text,"guard_matched",&guard_matched,0) &&
        field(text,"invalid_size_result",&invalid,1);
    char identity[80]; snprintf(identity,sizeof(identity),"\nbuild_id=%s\n",VI_BUILD_ID);
    r.valid=parsed && strstr(text,identity) && abi==VI_ABI && r.info_result==0 && magic==VI_MAGIC && size==112 &&
        (int)r.build_result>=0 && matched==1 && (int32_t)invalid==VI_E_ARGUMENT && r.caller==r.user && (int)r.shell>0;
    if(mode==1) r.valid=r.valid && r.user==(unsigned)sceKernelGetProcessId() && r.user!=r.shell && !r.guard && (int32_t)r.guard_result==VI_E_DENIED;
    else r.valid=r.valid && r.user==r.shell && r.guard==1 && (int)r.guard_result>=0 && guard_matched==1;
    journal(mode==1?"self report valid":"shell report valid",r.valid?0:-1); return r;
}
static void collect_entry(SceUID target) {
    char path[160],entry[2048];
    snprintf(path,sizeof(path),ROOT "/proxy-entry-%08x.log",(unsigned)target);
    int fd=sceIoOpen(path,SCE_O_RDONLY,0); journal("proxy entry log open",fd);
    if(fd<0) return;
    int n=sceIoRead(fd,entry,sizeof(entry)); sceIoClose(fd);
    if(n<=0 || n==(int)sizeof(entry)) { journal("proxy entry log size invalid",n); return; }
    snprintf(path,sizeof(path),"%s/%s-entry.log",run_directory,job.mode==1?"self":"shell");
    fd=sceIoOpen(path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    journal("proxy entry archive open",fd);
    if(fd>=0) { int written=sceIoWrite(fd,entry,(unsigned)n); sceIoClose(fd); journal("proxy entry archive write",written); }
}
static int entry_finished(SceUID target) {
    char path[160],entry[2049];
    snprintf(path,sizeof(path),ROOT "/proxy-entry-%08x.log",(unsigned)target);
    int fd=sceIoOpen(path,SCE_O_RDONLY,0);if(fd<0) return 0;
    int n=sceIoRead(fd,entry,sizeof(entry)-1);sceIoClose(fd);
    if(n<1 || n==(int)sizeof(entry)-1) return 0;
    entry[n]=0;
    return viEntryComplete(entry,VI_BUILD_ID,job.run);
}
static int probe(unsigned args,void *arg) {
    (void)args; (void)arg;
    __atomic_store_n(&phase,1,__ATOMIC_RELEASE);
    tai_module_args_t load={0}; load.size=sizeof(load); load.pid=KERNEL_PID;
    if(kernel<0) {
        /* Syscall exporters cannot be hot-unloaded. A persistent guard also
           prevents a second load after this application's process exits. */
        int lock=sceIoOpen(SESSION_LOCK,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
        journal("one-load session guard",lock);
        if(lock<0) { previous_session=1; goto done; }
        int written=sceIoWrite(lock,&job,sizeof(job)); int closed=sceIoClose(lock);
        journal("session guard write",written); journal("session guard close",closed);
        if(written!=(int)sizeof(job) || closed<0) { previous_session=1; goto done; }
        SceUID loaded=taiLoadStartKernelModuleForUser(MODULE_ROOT "vi_kernel.skprx",&load);
        __atomic_store_n(&kernel,loaded,__ATOMIC_RELEASE);
        journal("kernel load/start",kernel);
        if(kernel<0) { previous_session=1; goto done; }
    } else journal("reuse this run's kernel helper",kernel);
    __atomic_store_n(&phase,2,__ATOMIC_RELEASE);
    SceUID target=job.mode==1?sceKernelGetProcessId():(SceUID)self_result.shell;
    /* The Shell proxy reads the fresh on-disk session record. Its module entry
       does not depend on copying startup arguments into another process. */
    load.pid=target; load.args=job.mode==1?sizeof(job):0; load.argp=job.mode==1?&job:0;
    int start_result=-1;
    SceUID proxy=job.mode==1?
        sceKernelLoadStartModule(MODULE_ROOT "vi_proxy.suprx",sizeof(job),&job,0,0,&start_result):
        taiLoadStartModuleForPidForUser(MODULE_ROOT "vi_proxy.suprx",&load);
    journal(job.mode==1?"self proxy load/start":"shell proxy load/start",proxy);
    if(job.mode==1) journal("self proxy module_start",start_result);
    if(proxy>=0) {
        __atomic_store_n(&phase,3,__ATOMIC_RELEASE);
        if(job.mode==2) {
            uint64_t deadline=sceKernelGetProcessTimeWide()+3000000;
            while(!entry_finished(target) && sceKernelGetProcessTimeWide()<deadline) sceKernelDelayThread(20000);
            if(!entry_finished(target)) {
                collect_entry(target);journal("Shell diagnostic completion timeout; proxy retained until reboot",-1);
                cleanup_ok=0;goto retain_kernel;
            }
        }
        if(job.mode==1) self_result=report(job.mode); else shell_result=report(job.mode);
        if(job.mode==1 && start_result!=SCE_KERNEL_START_SUCCESS) self_result.valid=0;
        collect_entry(target);
        tai_module_args_t stop={0}; stop.size=sizeof(stop); stop.pid=target; int stop_result=0;
        int result=job.mode==1?sceKernelStopUnloadModule(proxy,0,0,0,0,&stop_result):taiStopUnloadModuleForPidForUser(proxy,&stop,0,&stop_result);
        journal("proxy stop/unload",result); journal("proxy module_stop",stop_result);
        if(result<0 || stop_result!=SCE_KERNEL_STOP_SUCCESS) cleanup_ok=0;
    }
retain_kernel:
    __atomic_store_n(&phase,4,__ATOMIC_RELEASE);
    journal("read-only kernel retained until normal reboot",kernel);
done:
    __atomic_store_n(&phase,5,__ATOMIC_RELEASE);
    __atomic_store_n(&busy,0,__ATOMIC_RELEASE); return 0;
}
static void begin(unsigned mode) {
    if(__atomic_load_n(&busy,__ATOMIC_ACQUIRE) || !storage_ok || !cleanup_ok || previous_session) return;
    if(thread>=0) { sceKernelWaitThreadEnd(thread,0,0); sceKernelDeleteThread(thread); thread=-1; }
    job.mode=mode;
    __atomic_store_n(&phase,0,__ATOMIC_RELEASE); __atomic_store_n(&busy,1,__ATOMIC_RELEASE);
    thread=sceKernelCreateThread("control-inspector",probe,0x10000100,32*1024,0,0,0);
    if(thread<0) { journal("probe thread create",thread); __atomic_store_n(&busy,0,__ATOMIC_RELEASE); return; }
    int result=sceKernelStartThread(thread,0,0); journal("probe thread start",result);
    if(result<0) { sceKernelDeleteThread(thread); thread=-1; __atomic_store_n(&busy,0,__ATOMIC_RELEASE); }
}
static void text(float y,unsigned color,const char *format,...) {
    char line[200]; va_list args; va_start(args,format); vsnprintf(line,sizeof(line),format,args); va_end(args);
    vita2d_pgf_draw_text(font,26,(int)y,color,0.87f,line);
}
static void show(float y,const char *title,const Result *r,int attempted) {
    unsigned color=r->valid?COLOR(64,220,191):COLOR(255,197,98);
    text(y,color,"%s: %s",title,r->available?(r->valid?"PASS":"CHECK REPORT"):attempted?"NO REPORT":"not run");
    if(r->available) {
        text(y+29,COLOR(210,221,239),"Caller %08x  Shell %08x  Shell guard %u",r->caller,r->shell,r->guard);
        text(y+57,COLOR(210,221,239),"Info %08x  Identity %08x  Guarded identity %08x",r->info_result,r->build_result,r->guard_result);
    }
}
int main(void) {
    if(vita2d_init()<0) return 1;
    font=vita2d_load_default_pgf(); if(!font) { vita2d_fini(); return 1; }
    vita2d_set_vblank_wait(1); vita2d_set_clear_color(COLOR(10,17,29));
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    sceIoMkdir(ROOT,0700|SCE_S_IRSYS|SCE_S_IWSYS);
    job.magic=VI_ARGS_MAGIC;
    for(unsigned attempt=0;attempt<8;attempt++) {
        snprintf(job.run,sizeof(job.run),"%016llx%08x%08x",(unsigned long long)sceKernelGetProcessTimeWide(),(unsigned)sceKernelGetProcessId(),++run_counter);
        snprintf(run_directory,sizeof(run_directory),ROOT "/%s",job.run);
        if(sceIoMkdir(run_directory,0700|SCE_S_IRSYS|SCE_S_IWSYS)>=0) { storage_ok=1; break; }
    }
    snprintf(journal_path,sizeof(journal_path),"%s/app.log",run_directory);
    journal("app ready; no helper loaded",storage_ok?0:-1);
    int lock=sceIoOpen(SESSION_LOCK,SCE_O_RDONLY,0);
    if(lock>=0) { sceIoClose(lock); previous_session=1; }
    else if(lock!=(int)0x80010002u) previous_session=1;
    journal("previous session guard check",lock);
    unsigned previous=0; int own_started=0,shell_started=0;
    while(1) {
        SceCtrlData input={0}; int sampled=sceCtrlPeekBufferPositive(0,&input,1);
        unsigned buttons=sampled>0?input.buttons:0,pressed=buttons&~previous; previous=buttons;
        int active=__atomic_load_n(&busy,__ATOMIC_ACQUIRE);
        if(!active) {
            if((buttons&(SCE_CTRL_START|SCE_CTRL_SELECT))==(SCE_CTRL_START|SCE_CTRL_SELECT)) break;
            if((pressed&SCE_CTRL_CROSS) && !own_started) { own_started=1; begin(1); }
            if(!__atomic_load_n(&busy,__ATOMIC_ACQUIRE) && (pressed&SCE_CTRL_SQUARE) && self_result.valid && !shell_started) { shell_started=1; begin(2); }
        }
        active=__atomic_load_n(&busy,__ATOMIC_ACQUIRE);
        vita2d_start_drawing(); vita2d_clear_screen();
        text(39,COLOR(64,220,191),"CONTROL INSPECTOR " VI_VERSION);
        text(73,COLOR(210,221,239),"Read-only checks. Boot configuration stays unchanged.");
        text(109,COLOR(210,221,239),"CROSS: test this app.  SQUARE: test the running system shell.");
        if(active) {
            const char *stages[]={"Preparing","Loading read-only helper","Loading diagnostic","Reading result","Releasing diagnostic","Finished"};
            int p=__atomic_load_n(&phase,__ATOMIC_ACQUIRE); if(p<0 || p>5) p=0;
            text(155,COLOR(255,197,98),"%s...  Wait for this check to finish.",stages[p]);
        } else {
            show(158,"APP",&self_result,own_started); show(269,"SYSTEM SHELL",&shell_result,shell_started);
            if(!storage_ok) text(380,COLOR(255,197,98),"Report storage unavailable; checks are disabled.");
            else if(previous_session) text(380,COLOR(255,197,98),"Earlier session found. Exit, reboot, then reopen FTP.");
            else if(!cleanup_ok) text(380,COLOR(255,197,98),"Cleanup failed. Exit and reboot normally before another run.");
            else text(380,COLOR(210,221,239),"%s",self_result.valid?"App check passed. SQUARE is available.":own_started?"Check ended. Exit and reopen FTP to collect the report.":"Press CROSS once to start the app check.");
        }
        text(450,COLOR(151,170,195),__atomic_load_n(&kernel,__ATOMIC_ACQUIRE)>=0?"Read-only helper stays loaded until reboot; no input/display hooks.":"Reports saved for FTP collection. One helper load per reboot.");
        text(510,COLOR(151,170,195),"START + SELECT: exit after a check finishes.");
        vita2d_end_drawing(); vita2d_swap_buffers();
    }
    if(thread>=0) { sceKernelWaitThreadEnd(thread,0,0); sceKernelDeleteThread(thread); }
    journal("normal exit",0);
    vita2d_wait_rendering_done(); vita2d_free_pgf(font); vita2d_fini(); sceKernelExitProcess(0); return 0;
}
