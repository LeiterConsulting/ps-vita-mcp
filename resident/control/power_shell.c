#include "control_platform.h"
#include "power_policy.h"
#include <psp2/kernel/threadmgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/motion.h>
#include <psp2/touch.h>
static SceUID mutex=-1,thread=-1;
static RPState state;
static int active;
static void lock(void) { sceKernelLockMutex(mutex,1,0); }
static void unlock(void) { sceKernelUnlockMutex(mutex,1); }
static int absolute(int v) { return v<0?-v:v; }
int rp_set(const RPConfig *c) {
    if(mutex<0||!rp_valid(c)) return -1;
    lock();rp_lease(&state,c,r_now());unlock();return 0;
}
int rp_read(RPState *out) { if(mutex<0) return -1;lock();R_MEMCPY(out,&state,sizeof(state));unlock();return 0; }
static int worker(unsigned args,void *arg) {
    (void)args;(void)arg;int sensor_owned=0,sensor_started=0,initialized=0,consecutive=0;
    float baseline[3]={0};uint64_t previous_sensor=0,changed_at=0;
    while(__atomic_load_n(&active,__ATOMIC_ACQUIRE)) {
        uint64_t now=r_now();lock();int working=state.expires_ms>now;unlock();
        uint32_t activity=0;int motion_result=-1,motion_valid=0;
        RTouchActivity physical={0};int touch_result=-1;
        if(working) {
            if(!sensor_started) { int result=sceMotionStartSampling();sensor_owned=result==0;sensor_started=1; }
            SceMotionState motion={0};motion_result=sceMotionGetState(&motion);
            if(motion_result>=0) {
                if(motion.hostTimestamp!=previous_sensor) { changed_at=now;previous_sensor=motion.hostTimestamp; }
                float acc[3]={motion.acceleration.x,motion.acceleration.y,motion.acceleration.z},gyro[3]={motion.angularVelocity.x,motion.angularVelocity.y,motion.angularVelocity.z};
                int moving=rp_motion(acc,gyro,baseline,&initialized,&consecutive);
                motion_valid=moving>=0&&motion.hostTimestamp&&now-changed_at<500;
                if(motion_valid&&moving) activity|=8;
            }
            RReadback input={0};
            if(rc_readback(&input)>=0&&input.sample_result>0) {
                uint32_t synthetic=input.lease.active?input.lease.input.buttons:0;
                if(input.buttons&~synthetic) activity|=1;
                int sticks[4]={(int)input.lx,(int)input.ly,(int)input.rx,(int)input.ry};
                uint32_t requested[4]={input.lease.input.lx,input.lease.input.ly,input.lease.input.rx,input.lease.input.ry};
                for(unsigned i=0;i<4;i++) {
                    if(input.lease.active&&(input.lease.input.flags&(i<2?1u:2u))) sticks[i]-=(int)requested[i]-128;
                    if(absolute(sticks[i]-128)>16) activity|=2;
                }
            }
            for(unsigned panel=0;panel<2;panel++) {
                /* Native activity comes only from the foreground-scoped cache;
                   this read also lets Shell's own sampled panels enter it. */
                SceTouchData touch={0};sceTouchPeek(panel,&touch,1);
            }
            touch_result=vitaControlTouchActivity(&physical,sizeof(physical));
            if(touch_result>=0&&physical.magic==RC_TOUCH_MAGIC&&physical.abi==RC_ABI&&physical.panels<=3&&physical.sampled_ms<=r_now()&&r_now()-physical.sampled_ms<500) {
                if(physical.panels) activity|=4;
            } else { touch_result=-1;R_MEMSET(&physical,0,sizeof(physical)); }
        } else {
            if(sensor_owned) sceMotionStopSampling();
            sensor_owned=sensor_started=initialized=consecutive=0;previous_sensor=0;
        }
        int brightness=vitaControlBrightness(-1);
        lock();state.motion_result=motion_result;state.motion_valid=motion_valid;
        state.touch_result=touch_result;state.touch_panels=physical.panels;state.touch_pid=physical.foreground_pid;
        state.touch_sample_ms=physical.sampled_ms;
        R_MEMCPY(state.touch_diagnostics,physical.panel,sizeof(physical.panel));
        RPAction action=rp_step(&state,now,r_network_ready(),brightness,activity,motion_valid);
        if(action.keep_awake&&now-state.last_tick_ms>=1000) {
            /* Timer refreshes leave saved sleep settings and explicit power-button sleep intact. */
            int result=sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND);
            int display=sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_OLED_OFF);
            int dim=sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_OLED_DIMMING);
            state.tick_result=result<0?result:display<0?display:dim;state.last_tick_ms=now;
        }
        if(action.brightness>=21) rp_applied(&state,action.brightness,vitaControlBrightness(action.brightness));
        unlock();r_delay(100);
    }
    lock();RPAction restore=rp_step(&state,r_now(),0,vitaControlBrightness(-1),0,0);
    if(restore.brightness>=21) rp_applied(&state,restore.brightness,vitaControlBrightness(restore.brightness));
    unlock();
    if(sensor_owned) sceMotionStopSampling();
    return 0;
}
int rp_start(void) {
    mutex=sceKernelCreateMutex("control-work-power",0,0,0);if(mutex<0) return -1;
    state.idle_ms=30000;state.dim_percent=20;state.current=state.motion_result=-1;
    __atomic_store_n(&active,1,__ATOMIC_RELEASE);thread=sceKernelCreateThread("control-work-power",worker,0x60,32768,0,0,0);
    if(thread<0||sceKernelStartThread(thread,0,0)<0) { __atomic_store_n(&active,0,__ATOMIC_RELEASE);if(thread>=0) sceKernelDeleteThread(thread);thread=-1;sceKernelDeleteMutex(mutex);mutex=-1;return -1; }return 0;
}
int rp_stop(void) {
    __atomic_store_n(&active,0,__ATOMIC_RELEASE);
    if(thread>=0) { SceUInt timeout=5000000;if(sceKernelWaitThreadEnd(thread,0,&timeout)<0) return -1;sceKernelDeleteThread(thread);thread=-1; }
    if(mutex>=0) { sceKernelDeleteMutex(mutex);mutex=-1; }return 0;
}
