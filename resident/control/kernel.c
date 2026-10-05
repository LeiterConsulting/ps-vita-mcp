/* Adapted from devnoname120/vitacompanion, MIT. See LICENSE.vitacompanion. */
#include "api.h"
#include "lease.h"
#include "button_map.h"
#include "touch_activity.h"
#include "pairing_privacy.h"
#include <psp2kern/power.h>
int module_get_export_func(SceUID pid,const char *module,uint32_t library,uint32_t function,uintptr_t *address);
#include <psp2kern/display.h>
#include <psp2kern/kernel/cpu.h>
#include <psp2kern/kernel/sysroot.h>
#include <psp2kern/kernel/sysmem/data_transfers.h>

#include <psp2/touch.h>
#include <psp2kern/ctrl.h>
#include <psp2kern/kernel/modulemgr.h>
#include <psp2kern/kernel/threadmgr.h>
#include <stdint.h>
#include <taihen.h>

#define CTRL_REFRESH_US (8 * 1000)
#define CTRL_EMULATION_SAMPLES 2
#define FRONT_TOUCH_REPORTS 6
#define REAR_TOUCH_REPORTS 4
#define SYNTHETIC_TOUCH_ID_BASE 0x70
#define USER_BUTTON_MASK 0x0000FFFF

typedef struct {
    int active;
    uint8_t x;
    uint8_t y;
} analog_state;

typedef struct {
    int active;
    uint16_t x;
    uint16_t y;
} touch_state;

static SceUID state_mutex = -1;
static SceUID ctrl_thread_id = -1;
static volatile int ctrl_thread_running;
static uint32_t button_state;
static RLease lease;
static SceUID capture_mutex=-1;
static uint32_t capture_sequence;
static unsigned char capture_row[8192], output_row[1440];
static analog_state analog_states[2];
static touch_state touch_states[2][4];
static RTState physical_touch;
static int pairing_process_allowed(SceUID pid) {
    char title[32]={0};int result=ksceKernelGetProcessTitleId(pid,title,sizeof(title));
    return rc_pairing_process_allowed(result,title);
}

static SceUID touch_hook_ids[4] = {-1, -1, -1, -1};
static tai_hook_ref_t touch_peek_ref;
static tai_hook_ref_t touch_peek_region_ref;
static tai_hook_ref_t touch_read_ref;
static tai_hook_ref_t touch_read_region_ref;

static void state_lock(void)
{
    if (state_mutex >= 0)
        ksceKernelLockMutex(state_mutex, 1, NULL);
}

static void state_unlock(void)
{
    if (state_mutex >= 0)
        ksceKernelUnlockMutex(state_mutex, 1);
}

static void clear_state(uint32_t reason)
{
    int port;
    int slot;

    button_state = 0;
    rlease_clear(&lease,(uint64_t)ksceKernelGetSystemTimeWide()/1000,reason);
    for (port = 0; port < 2; ++port)
    {
        analog_states[port].active = 0;
        analog_states[port].x = 128;
        analog_states[port].y = 128;
    }

    for (port = 0; port < 2; ++port)
    {
        for (slot = 0; slot < 4; ++slot)
        {
            touch_states[port][slot].active = 0;
            touch_states[port][slot].x = 0;
            touch_states[port][slot].y = 0;
        }
    }
}

static void reset_ctrl_emulation(void)
{
    ksceCtrlSetButtonEmulation(0, 3, 0, 0, CTRL_EMULATION_SAMPLES);
    ksceCtrlSetAnalogEmulation(0, 3,
        128, 128,
        128, 128,
        128, 128,
        128, 128, 0);
}

static int ctrl_thread(unsigned int args, void *argp)
{
    uint32_t last_buttons = 0;
    int analog_was_active = 0;

    (void)args;
    (void)argp;

    while (ctrl_thread_running)
    {
        uint32_t buttons;
        analog_state left;
        analog_state right;
        int analog_active;

        state_lock();
        if(lease.active) {
            SceDisplayFrameBufInfo current={0}; current.size=sizeof(current);
            int frame_result=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),0,&current);
            if(frame_result<0||!current.paddr) frame_result=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),1,&current);
            uint32_t reason=rlease_reason(&lease,(uint64_t)ksceKernelGetSystemTimeWide()/1000,frame_result<0?-1:current.pid);
            if(reason) clear_state(reason);
        }
        buttons = button_state;
        left = analog_states[0];
        right = analog_states[1];

        if (buttons != 0 || last_buttons != 0)
        {
            uint32_t driver_buttons=rc_driver_buttons(buttons);
            ksceCtrlSetButtonEmulation(
                0, 3, driver_buttons & USER_BUTTON_MASK, driver_buttons,
                CTRL_EMULATION_SAMPLES);
        }
        last_buttons = buttons;

        analog_active = left.active || right.active;
        if (analog_active)
        {
            uint8_t lx = left.active ? left.x : 128;
            uint8_t ly = left.active ? left.y : 128;
            uint8_t rx = right.active ? right.x : 128;
            uint8_t ry = right.active ? right.y : 128;

            ksceCtrlSetAnalogEmulation(
                0, 3, lx, ly, rx, ry, lx, ly, rx, ry,
                CTRL_EMULATION_SAMPLES);
        }
        else if (analog_was_active)
        {
            ksceCtrlSetAnalogEmulation(0, 3,
                128,
                128,
                128,
                128,
                128,
                128,
                128,
                128, 0);
        }
        analog_was_active = analog_active;
        state_unlock();

        ksceKernelDelayThread(CTRL_REFRESH_US);
    }

    reset_ctrl_emulation();
    return 0;
}

static void patch_touch_data(unsigned int port, SceTouchData *data,
    unsigned int count)
{
    touch_state points[4];
    unsigned int maximum_reports;
    unsigned int buffer_index;
    int slot;

    if (port > 1 || !data)
        return;

    state_lock();
    /* The foreground application receives physical samples that Shell may
       not receive. Observe native contacts before our augmentation, including
       when there is no synthetic lease. Bound all source samples and retain
       only a short foreground-scoped activity window. */
    if(count<=64) {
        uint64_t now=(uint64_t)ksceKernelGetSystemTimeWide()/1000;
        int32_t pid=ksceKernelGetProcessId();
        for(unsigned n=0;n<count;n++) {
            uint32_t contacts=0;
            for(unsigned t=0;t<data[n].reportNum&&t<SCE_TOUCH_MAX_REPORT;t++) {
                const SceTouchReport *contact=&data[n].report[t];int emulated=0;
                if(lease.active&&pid==lease.input.target_pid)
                    for(unsigned p=0;p<4;p++) {
                        touch_state point=touch_states[port][p];
                        if(rt_synthetic(contact->id,contact->x,contact->y,point.active,SYNTHETIC_TOUCH_ID_BASE+p,point.x,point.y)) emulated=1;
                    }
                if(!emulated) contacts++;
            }
            if(data[n].reportNum<=SCE_TOUCH_MAX_REPORT)
                rt_observe(&physical_touch,port,pid,contacts,data[n].timeStamp,now);
        }
    }
    if(!lease.active||ksceKernelGetProcessId()!=lease.input.target_pid) { state_unlock(); return; }
    if(lease.active&&(uint64_t)ksceKernelGetSystemTimeWide()/1000>=lease.expires_ms) clear_state(RC_RELEASE_EXPIRED);
    for (slot = 0; slot < 4; ++slot)
        points[slot] = touch_states[port][slot];
    state_unlock();

    maximum_reports = port == 0
        ? FRONT_TOUCH_REPORTS : REAR_TOUCH_REPORTS;

    for (buffer_index = 0; buffer_index < count; ++buffer_index)
    {
        SceTouchData *current = &data[buffer_index];

        for (slot = 0; slot < 4; ++slot)
        {
            SceTouchReport *report;

            if (!points[slot].active ||
                current->reportNum >= maximum_reports)
                continue;

            report = &current->report[current->reportNum++];
            report->id = (uint8_t)(SYNTHETIC_TOUCH_ID_BASE + slot);
            report->force = 0x80;
            report->x = (int16_t)points[slot].x;
            report->y = (int16_t)points[slot].y;
            report->reserved[0] = 0;
            report->reserved[1] = 0;
            report->reserved[2] = 0;
            report->reserved[3] = 0;
            report->reserved[4] = 0;
            report->reserved[5] = 0;
            report->reserved[6] = 0;
            report->reserved[7] = 0;
            report->info = 0;
        }
    }
}

static int touch_peek_hook(unsigned int port, SceTouchData *data,
    unsigned int count)
{
    int result = TAI_CONTINUE(int, touch_peek_ref, port, data, count);

    if (result > 0)
        patch_touch_data(port, data, (unsigned int)result);
    return result;
}

static int touch_peek_region_hook(unsigned int port, SceTouchData *data,
    unsigned int count, int region)
{
    int result = TAI_CONTINUE(int, touch_peek_region_ref,
        port, data, count, region);

    if (result > 0)
        patch_touch_data(port, data, (unsigned int)result);
    return result;
}

static int touch_read_hook(unsigned int port, SceTouchData *data,
    unsigned int count)
{
    int result = TAI_CONTINUE(int, touch_read_ref, port, data, count);

    if (result > 0)
        patch_touch_data(port, data, (unsigned int)result);
    return result;
}

static int touch_read_region_hook(unsigned int port, SceTouchData *data,
    unsigned int count, int region)
{
    int result = TAI_CONTINUE(int, touch_read_region_ref,
        port, data, count, region);

    if (result > 0)
        patch_touch_data(port, data, (unsigned int)result);
    return result;
}

static void release_touch_hooks(void)
{
    tai_hook_ref_t *refs[] = {
        &touch_peek_ref,
        &touch_peek_region_ref,
        &touch_read_ref,
        &touch_read_region_ref
    };
    int i;

    for (i = 3; i >= 0; --i)
    {
        if (touch_hook_ids[i] >= 0)
        {
            taiHookReleaseForKernel(touch_hook_ids[i], *refs[i]);
            touch_hook_ids[i] = -1;
        }
    }
}

static int install_touch_hooks(void)
{
    static const uint32_t nids[4] = {
        0xBAD1960B,
        0x9B3F7207,
        0x70C8AACE,
        0x9A91F624
    };
    static const void *functions[4] = {
        touch_peek_hook,
        touch_peek_region_hook,
        touch_read_hook,
        touch_read_region_hook
    };
    tai_hook_ref_t *refs[4] = {
        &touch_peek_ref,
        &touch_peek_region_ref,
        &touch_read_ref,
        &touch_read_region_ref
    };
    tai_module_info_t info;
    const char *module_name = "SceTouch";
    int i;

    info.size = sizeof(info);
    if (taiGetModuleInfoForKernel(KERNEL_PID, module_name, &info) < 0)
    {
        module_name = "SceTouchDummy";
        info.size = sizeof(info);
        if (taiGetModuleInfoForKernel(KERNEL_PID, module_name, &info) < 0)
            return -1;
    }

    for (i = 0; i < 4; ++i)
    {
        touch_hook_ids[i] = taiHookFunctionExportForKernel(
            KERNEL_PID, refs[i], module_name, TAI_ANY_LIBRARY,
            nids[i], functions[i]);
        if (touch_hook_ids[i] < 0)
        {
            int result = touch_hook_ids[i];
            release_touch_hooks();
            return result;
        }
    }

    return 0;
}

/* These syscalls expose bounded operations only to SceShell. */
static int shell_caller(void) {
    SceUID caller=ksceKernelGetProcessId(),shell=ksceKernelSysrootGetShellPid();
    return caller>0 && shell>0 && caller==shell;
}
/* Read-only readiness used by the foreground starter before targeting Shell. */
int rc_bootstrap_ready(void) {
    if(state_mutex<0 || capture_mutex<0 || !ctrl_thread_running) return 0;
    for(unsigned i=0;i<4;i++) if(touch_hook_ids[i]<0) return 0;
    return 1;
}
int vitaControlVersion(void) { return RC_ABI; }
int vitaControlBuildId(char *out,unsigned size) {
    int state,result=-1; ENTER_SYSCALL(state);
    if(shell_caller()&&size==65) result=ksceKernelCopyToUser(out,R_BUILD_ID,65);
    EXIT_SYSCALL(state); return result;
}
int vitaControlInput(const RInput *user_input,unsigned size) {
    int state,result=-1; ENTER_SYSCALL(state);
    RInput input;
    if(shell_caller()&&size==sizeof(input)&&ksceKernelCopyFromUser(&input,user_input,sizeof(input))>=0&&rlease_valid(&input)) {
        SceDisplayFrameBufInfo fb={0}; fb.size=sizeof(fb);
        int got=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),0,&fb);
        if(got<0||!fb.paddr) got=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),1,&fb);
        if(got>=0&&fb.pid==input.target_pid&&pairing_process_allowed(fb.pid)) {
            state_lock(); clear_state(RC_RELEASE_REPLACED);
            rlease_apply(&lease,&input,(uint64_t)ksceKernelGetSystemTimeWide()/1000);
            button_state=input.buttons;
            analog_states[0]=(analog_state){(input.flags&1)!=0,input.lx,input.ly};
            analog_states[1]=(analog_state){(input.flags&2)!=0,input.rx,input.ry};
            touch_states[0][0]=(touch_state){(input.flags&4)!=0,input.fx,input.fy};
            touch_states[1][0]=(touch_state){(input.flags&8)!=0,input.bx,input.by};
            state_unlock(); result=0;
        } else result=-2;
    }
    EXIT_SYSCALL(state); return result;
}
int vitaControlRelease(void) {
    int state,result=-1; ENTER_SYSCALL(state);
    if(shell_caller()) { state_lock(); clear_state(RC_RELEASE_MANUAL); reset_ctrl_emulation(); state_unlock(); result=0; }
    EXIT_SYSCALL(state); return result;
}
int vitaControlBrightness(int value) {
    static unsigned (*getter)(void);
    int state,result=-1;ENTER_SYSCALL(state);
    if(shell_caller()) {
        if(value==-1) {
            if(!getter) {
                uintptr_t address=0;
                if(module_get_export_func(KERNEL_PID,"SceOled",0x60C7478A,0x43EF811A,&address)>=0) getter=(unsigned (*)(void))address;
                else if(module_get_export_func(KERNEL_PID,"SceLcd",0xFA916D71,0x3A6D6AC3,&address)>=0) getter=(unsigned (*)(void))address;
            }
            if(getter) { unsigned current=getter();result=current<=65536?(int)current:-2; }
        } else if(value>=21&&value<=65536) result=kscePowerSetDisplayBrightness(value);
    }
    EXIT_SYSCALL(state);return result;
}
int vitaControlReadback(RReadback *user_out,unsigned size) {
    int state,result=-1; ENTER_SYSCALL(state);
    if(shell_caller()&&size==sizeof(RReadback)) {
        RReadback value={0}; value.magic=RC_READ_MAGIC; value.abi=RC_ABI;
        value.sample_ms=(uint64_t)ksceKernelGetSystemTimeWide()/1000;
        state_lock(); value.lease=lease; state_unlock();
        SceCtrlData pad={0}; value.sample_result=ksceCtrlPeekBufferPositive(0,&pad,1);
        value.buttons=rc_vita_buttons(pad.buttons); value.lx=pad.lx; value.ly=pad.ly; value.rx=pad.rx; value.ry=pad.ry;
        result=ksceKernelCopyToUser(user_out,&value,sizeof(value));
    }
    EXIT_SYSCALL(state); return result;
}
int vitaControlTouchActivity(RTouchActivity *user_out,unsigned size) {
    int state,result=-1;ENTER_SYSCALL(state);
    if(shell_caller()&&size==sizeof(RTouchActivity)) {
        SceDisplayFrameBufInfo fb={0};fb.size=sizeof(fb);
        int got=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),0,&fb);
        if(got<0||!fb.paddr) got=ksceDisplayGetProcFrameBufInternal(-1,ksceDisplayGetPrimaryHead(),1,&fb);
        RTouchActivity value={0};value.magic=RC_TOUCH_MAGIC;value.abi=RC_ABI;
        value.sampled_ms=(uint64_t)ksceKernelGetSystemTimeWide()/1000;
        if(got>=0&&fb.paddr&&fb.pid>0) {
            value.foreground_pid=fb.pid;
        }
        state_lock();value.panels=rt_panels(&physical_touch,value.foreground_pid,value.sampled_ms);
        for(unsigned p=0;p<2;p++) {
            RTouchPanel *out=&value.panel[p];const RTEvent *e=rt_reader(&physical_touch,p,value.foreground_pid);
            out->last_reader_pid=physical_touch.last_pid[p];out->hook_reads=physical_touch.reads[p];
            if(e) {
                out->reader_pid=e->pid;out->native_contacts=e->count;out->reads=e->reads;out->advances=e->advances;
                out->source_ticks=e->source_ticks;out->received_ms=e->received_ms;out->changed_ms=e->changed_ms;
            }
        }
        state_unlock();
        result=ksceKernelCopyToUser(user_out,&value,sizeof(value));
    }
    EXIT_SYSCALL(state);return result;
}
int vitaControlCapture(void *user_pixels,unsigned capacity,RFrame *user_frame,unsigned scale) {
    int state,result=-1; ENTER_SYSCALL(state);
    if(!shell_caller()||(scale!=2&&scale!=4)) { EXIT_SYSCALL(state); return -1; }
    ksceKernelLockMutex(capture_mutex,1,0);
    SceDisplayFrameBufInfo fb={0}; fb.size=sizeof(fb);
    int head=ksceDisplayGetPrimaryHead(), index=0;
    result=ksceDisplayGetProcFrameBufInternal(-1,head,index,&fb);
    if(result<0||!fb.paddr) { index=1; result=ksceDisplayGetProcFrameBufInternal(-1,head,index,&fb); }
    RFrame frame={0}; frame.magic=RC_FRAME_MAGIC; frame.abi=RC_ABI;
    frame.started_us=ksceKernelGetSystemTimeWide();
    if(result>=0) {
        if(!pairing_process_allowed(fb.pid)||!fb.framebuf.base||fb.pid<=0||fb.framebuf.pixelformat!=SCE_DISPLAY_PIXELFORMAT_A8B8G8R8||
           fb.framebuf.width<4||fb.framebuf.width>960||fb.framebuf.height<4||fb.framebuf.height>544||
           fb.framebuf.pitch<fb.framebuf.width||fb.framebuf.pitch>2048) result=-3;
        else {
            frame.width=fb.framebuf.width/scale; frame.height=fb.framebuf.height/scale;
            frame.bytes=frame.width*frame.height*3; frame.pid=fb.pid; frame.vblank=fb.vblankcount;
            frame.source_width=fb.framebuf.width; frame.source_height=fb.framebuf.height; frame.sequence=++capture_sequence;
            if(capacity<frame.bytes) result=-4;
            else for(unsigned y=0;y<frame.height;y++) {
                const unsigned char *src=(unsigned char *)fb.framebuf.base+(size_t)y*scale*fb.framebuf.pitch*4;
                result=ksceKernelCopyFromUserProc(fb.pid,capture_row,src,fb.framebuf.width*4);
                if(result<0) break;
                for(unsigned x=0;x<frame.width;x++) for(unsigned c=0;c<3;c++) output_row[x*3+c]=capture_row[x*scale*4+c];
                result=ksceKernelCopyToUser((unsigned char *)user_pixels+y*frame.width*3,output_row,frame.width*3);
                if(result<0) break;
            }
            SceDisplayFrameBufInfo after={0}; after.size=sizeof(after);
            if(result>=0&&(ksceDisplayGetProcFrameBufInternal(-1,head,index,&after)<0||after.pid!=fb.pid)) result=-5;
            /* A live framebuffer copy may span multiple rendered frames; report this honestly. */
            frame.flags=1;
        }
    }
    frame.ended_us=ksceKernelGetSystemTimeWide();
    if(result>=0) result=ksceKernelCopyToUser(user_frame,&frame,sizeof(frame));
    ksceKernelUnlockMutex(capture_mutex,1);
    EXIT_SYSCALL(state); return result;
}

int module_start(SceSize argc, const void *args)
{
    int result;

    (void)argc;
    (void)args;

    clear_state(RC_RELEASE_STOP);
    state_mutex = ksceKernelCreateMutex(
        "vita-control-input", 0, 0, NULL);
    if (state_mutex < 0)
        return SCE_KERNEL_START_FAILED;

    capture_mutex=ksceKernelCreateMutex("vita-control-capture",0,0,NULL);
    if(capture_mutex<0) { ksceKernelDeleteMutex(state_mutex); state_mutex=-1; return SCE_KERNEL_START_FAILED; }
    result = install_touch_hooks();
    if (result < 0)
    {
        ksceKernelDeleteMutex(state_mutex);
        ksceKernelDeleteMutex(capture_mutex); capture_mutex=-1;
        state_mutex = -1;
        return SCE_KERNEL_START_FAILED;
    }

    ctrl_thread_id = ksceKernelCreateThread(
        "vita-control-lease", ctrl_thread,
        0x40, 0x1000, 0, 0, NULL);
    if (ctrl_thread_id < 0)
    {
        release_touch_hooks();
        ksceKernelDeleteMutex(state_mutex);
        ksceKernelDeleteMutex(capture_mutex); capture_mutex=-1;
        state_mutex = -1;
        return SCE_KERNEL_START_FAILED;
    }

    ctrl_thread_running = 1;
    result = ksceKernelStartThread(ctrl_thread_id, 0, NULL);
    if (result < 0)
    {
        ctrl_thread_running = 0;
        ksceKernelDeleteThread(ctrl_thread_id);
        ctrl_thread_id = -1;
        release_touch_hooks();
        ksceKernelDeleteMutex(state_mutex);
        ksceKernelDeleteMutex(capture_mutex); capture_mutex=-1;
        state_mutex = -1;
        return SCE_KERNEL_START_FAILED;
    }

    return SCE_KERNEL_START_SUCCESS;
}

int module_stop(SceSize argc, const void *args)
{
    (void)argc;
    (void)args;

    state_lock();
    clear_state(RC_RELEASE_STOP);
    state_unlock();

    ctrl_thread_running = 0;
    if (ctrl_thread_id >= 0)
    {
        SceUInt timeout=2000000;
        if(ksceKernelWaitThreadEnd(ctrl_thread_id, NULL, &timeout)<0) return SCE_KERNEL_STOP_CANCEL;
        ksceKernelDeleteThread(ctrl_thread_id);
        ctrl_thread_id = -1;
    }

    release_touch_hooks();
    reset_ctrl_emulation();
    if(capture_mutex>=0) { ksceKernelDeleteMutex(capture_mutex); capture_mutex=-1; }

    if (state_mutex >= 0)
    {
        ksceKernelDeleteMutex(state_mutex);
        state_mutex = -1;
    }

    return SCE_KERNEL_STOP_SUCCESS;
}

int _start(SceSize argc, const void *args)
    __attribute__((weak, alias("module_start")));
