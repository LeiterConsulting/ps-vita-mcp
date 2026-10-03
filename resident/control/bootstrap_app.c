#include "api.h"
#include <psp2/ctrl.h>
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <vita2d.h>
#include <taihen.h>
#include <stdio.h>
#include <string.h>
#define MODULE_ROOT "ux0:app/CHRS00011/"
#define COLOR(r,g,b) ((unsigned)(r)|((unsigned)(g)<<8)|((unsigned)(b)<<16)|0xff000000u)
static RBootstrapArgs job;
static char directory[128],log_path[160];
static volatile int busy,phase;
static int storage_ok,guard_present,attempted,outcome;
static SceUID thread=-1,kernel=-1,service=-1;
static void journal(const char *stage,int result) {
    char line[192];int n=snprintf(line,sizeof(line),"tick_us=%llu stage=%s result=0x%08x\n",(unsigned long long)sceKernelGetProcessTimeWide(),stage,(unsigned)result);
    if(n<=0 || (unsigned)n>=sizeof(line)) return;
    int fd=sceIoOpen(log_path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    if(fd>=0) { sceIoWrite(fd,line,(unsigned)n);sceIoClose(fd); }
}
static int start(unsigned size,void *arg) {
    (void)size;(void)arg;
    __atomic_store_n(&phase,1,__ATOMIC_RELEASE);
    int lock=sceIoOpen(RC_BOOT_GUARD,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    journal("one-load guard",lock);if(lock<0) goto done;
    int written=sceIoWrite(lock,&job,sizeof(job)),closed=sceIoClose(lock);
    journal("session guard write",written);journal("session guard close",closed);
    if(written!=(int)sizeof(job) || closed<0) goto done;
    /* Invalidate any previous service journal before submitting this pair. */
    int fd=sceIoOpen(RC_BOOT_ROOT "/startup.log",SCE_O_WRONLY|SCE_O_CREAT|SCE_O_TRUNC,0600|SCE_S_IRSYS|SCE_S_IWSYS);
    journal("service journal reset",fd);if(fd<0) goto done;
    if(sceIoClose(fd)<0) goto done;
    tai_module_args_t load={0};load.size=sizeof(load);load.pid=KERNEL_PID;
    journal("submitting runtime kernel",0);
    kernel=taiLoadStartKernelModuleForUser(MODULE_ROOT "vita_control_kernel.skprx",&load);
    journal("kernel load/start",kernel);if(kernel<0) goto done;
    __atomic_store_n(&phase,2,__ATOMIC_RELEASE);
    int start_result=-1,stop_result=-1;
    SceUID probe=sceKernelLoadStartModule(MODULE_ROOT "control_bootstrap_probe.suprx",sizeof(job),&job,0,0,&start_result);
    journal("bootstrap probe load/start",probe);journal("bootstrap probe module_start",start_result);
    if(probe<0) goto done;
    RBootstrapInfo info={0};char path[160];unsigned char extra=0;
    snprintf(path,sizeof(path),"%s/bootstrap.bin",directory);
    fd=sceIoOpen(path,SCE_O_RDONLY,0);int n=fd>=0?sceIoRead(fd,&info,sizeof(info)):-1;
    int tail=n==(int)sizeof(info)?sceIoRead(fd,&extra,1):-1;
    int close=fd>=0?sceIoClose(fd):-1;
    journal("bootstrap metadata read",n);journal("bootstrap metadata EOF",tail);
    int released=sceKernelStopUnloadModule(probe,0,0,0,0,&stop_result);
    journal("bootstrap probe stop/unload",released);journal("bootstrap probe module_stop",stop_result);
    if(start_result!=SCE_KERNEL_START_SUCCESS || released<0 || stop_result!=SCE_KERNEL_STOP_SUCCESS ||
       n!=(int)sizeof(info) || tail!=0 || close<0 || info.magic!=RC_BOOT_MAGIC || info.abi!=RC_ABI || info.size!=sizeof(info) || info.ready!=1 ||
       info.caller_before!=sceKernelGetProcessId() || info.caller_after!=info.caller_before || info.shell_pid<=0 ||
       info.shell_pid==info.caller_after || info.guard_allowed || info.build_id[64] || strcmp(info.build_id,R_BUILD_ID)) goto done;
    journal("matched kernel ready; positive Shell PID",info.shell_pid);
    __atomic_store_n(&phase,3,__ATOMIC_RELEASE);
    load.pid=info.shell_pid;load.args=0;load.argp=0;
    service=taiLoadStartModuleForPidForUser(MODULE_ROOT "vita_control.suprx",&load);
    journal("Shell service load/start (MCP acceptance pending)",service);
    if(service>=0) outcome=1;
done:
    journal("runtime modules retained until normal reboot",kernel);
    __atomic_store_n(&phase,4,__ATOMIC_RELEASE);__atomic_store_n(&busy,0,__ATOMIC_RELEASE);return 0;
}
int main(void) {
    if(vita2d_init()<0) return 1;
    vita2d_pgf *font=vita2d_load_default_pgf();if(!font) { vita2d_fini();return 1; }
    vita2d_set_vblank_wait(1);vita2d_set_clear_color(COLOR(10,17,29));sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    sceIoMkdir(RC_BOOT_ROOT,0700|SCE_S_IRSYS|SCE_S_IWSYS);
    sceIoMkdir(RC_BOOT_ROOT "/workspace",0700|SCE_S_IRSYS|SCE_S_IWSYS);
    job.magic=RC_BOOT_ARGS_MAGIC;job.mode=1;
    for(unsigned attempt=1;attempt<=8;attempt++) {
        snprintf(job.run,sizeof(job.run),"%016llx%08x%08x",(unsigned long long)sceKernelGetProcessTimeWide(),(unsigned)sceKernelGetProcessId(),attempt);
        snprintf(directory,sizeof(directory),RC_BOOT_ROOT "/%s",job.run);
        if(sceIoMkdir(directory,0700|SCE_S_IRSYS|SCE_S_IWSYS)>=0) { storage_ok=1;break; }
    }
    snprintf(log_path,sizeof(log_path),"%s/starter.log",directory);
    journal("Control Starter 01.00 ready; no modules submitted",storage_ok?0:-1);
    int fd=sceIoOpen(RC_BOOT_GUARD,SCE_O_RDONLY,0);
    if(fd>=0) { sceIoClose(fd);guard_present=1; }else if(fd!=(int)0x80010002u) guard_present=1;
    unsigned previous=0;
    while(1) {
        SceCtrlData input={0};int sampled=sceCtrlPeekBufferPositive(0,&input,1);
        unsigned buttons=sampled>0?input.buttons:0,pressed=buttons&~previous;previous=buttons;
        int active=__atomic_load_n(&busy,__ATOMIC_ACQUIRE);
        if(!active && (buttons&(SCE_CTRL_START|SCE_CTRL_SELECT))==(SCE_CTRL_START|SCE_CTRL_SELECT)) break;
        if(!active && (pressed&SCE_CTRL_CROSS) && storage_ok && !guard_present && !attempted) {
            attempted=1;__atomic_store_n(&busy,1,__ATOMIC_RELEASE);
            thread=sceKernelCreateThread("control-starter",start,0x40,32*1024,0,0,0);
            int result=thread>=0?sceKernelStartThread(thread,0,0):thread;
            journal("starter worker start",result);
            if(result<0) { if(thread>=0) sceKernelDeleteThread(thread);thread=-1;__atomic_store_n(&busy,0,__ATOMIC_RELEASE); }
        }
        active=__atomic_load_n(&busy,__ATOMIC_ACQUIRE);
        vita2d_start_drawing();vita2d_clear_screen();
        vita2d_pgf_draw_text(font,30,45,COLOR(64,220,191),1.2f,"CONTROL STARTER 01.00");
        vita2d_pgf_draw_text(font,30,91,COLOR(210,221,239),1.0f,"Start the control service after LiveArea has booted.");
        vita2d_pgf_draw_text(font,30,127,COLOR(210,221,239),1.0f,"Boot configuration stays unchanged. Reboot ends this session.");
        const char *message;
        if(active) { static const char *stages[]={"Preparing...","Loading runtime helper...","Checking matched helper...","Submitting Shell service...","Finished"};message=stages[__atomic_load_n(&phase,__ATOMIC_ACQUIRE)]; }
        else if(!storage_ok) message="Report storage unavailable. Exit and reopen FTP.";
        else if(guard_present) message="Earlier session found. Exit, reboot, then reopen FTP.";
        else if(outcome) message="MODULES LOADED. Exit and let the PC check the MCP service.";
        else if(attempted) message="LOAD CHECK FAILED. Exit and reopen FTP for the report.";
        else message="Press CROSS once to start the runtime control session.";
        vita2d_pgf_draw_text(font,30,218,COLOR(255,197,98),1.0f,message);
        vita2d_pgf_draw_text(font,30,295,COLOR(151,170,195),1.0f,"A loaded module is not yet a verified network service.");
        vita2d_pgf_draw_text(font,30,331,COLOR(151,170,195),1.0f,"PC tests will check identity, files, screen readback and short inputs.");
        vita2d_pgf_draw_text(font,30,505,COLOR(210,221,239),1.0f,"START + SELECT: exit after loading finishes.");
        vita2d_end_drawing();vita2d_swap_buffers();
    }
    if(thread>=0) { sceKernelWaitThreadEnd(thread,0,0);sceKernelDeleteThread(thread); }
    journal("normal exit",0);vita2d_wait_rendering_done();vita2d_free_pgf(font);vita2d_fini();sceKernelExitProcess(0);return 0;
}
