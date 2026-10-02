#include "platform.h"
#include "math_helpers.h"
#include <psp2/ctrl.h>
#include <psp2/touch.h>
#include <psp2/motion.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <vita2d.h>
#include <string.h>

static vita2d_pgf *font;
static SceTouchPanelInfo panels[2];
static int panel_result[2],touch_start[2],motion_start;
static uint32_t previous_buttons;
static uint64_t previous_time;
static float frame_accumulator;
static unsigned frames;
static float measured_fps=60;
static bool motion_sampling;

static void start_sensors(void) {
    touch_start[0]=sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT,SCE_TOUCH_SAMPLING_STATE_START);
    touch_start[1]=sceTouchSetSamplingState(SCE_TOUCH_PORT_BACK,SCE_TOUCH_SAMPLING_STATE_START);
    motion_start=sceMotionStartSampling();
    motion_sampling=motion_start>=0;
}
bool platform_init(void) {
    if(vita2d_init()<0) return false;
    vita2d_set_vblank_wait(1);
    vita2d_set_clear_color(COLOR(10,17,29));
    font=vita2d_load_default_pgf();
    if(!font) { vita2d_fini(); return false; }
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    panel_result[0]=sceTouchGetPanelInfo(SCE_TOUCH_PORT_FRONT,&panels[0]);
    panel_result[1]=sceTouchGetPanelInfo(SCE_TOUCH_PORT_BACK,&panels[1]);
    start_sensors();
    previous_time=sceKernelGetProcessTimeWide();
    return true;
}
static void poll_touch(unsigned port,TouchPanel *out) {
    SceTouchData data={0};
    out->panel_result=panel_result[port];
    out->start_result=touch_start[port];
    out->read_result=sceTouchPeek(port,&data,1);
    if(out->read_result<1 || out->panel_result<0) return;
    out->count=data.reportNum>MAX_TOUCHES?MAX_TOUCHES:(int)data.reportNum;
    SceTouchPanelInfo *p=&panels[port];
    // Map the front display and the rear active area independently.
    int minx=port?p->minAaX:p->minDispX, maxx=port?p->maxAaX:p->maxDispX;
    int miny=port?p->minAaY:p->minDispY, maxy=port?p->maxAaY:p->maxDispY;
    for(int n=0;n<out->count;n++) {
        out->points[n]=(Contact){data.report[n].id,
            normalize_touch(data.report[n].x,minx,maxx),normalize_touch(data.report[n].y,miny,maxy),
            data.report[n].x,data.report[n].y};
    }
}
void platform_poll(Input *out) {
    memset(out,0,sizeof(*out));
    out->lx=out->ly=out->rx=out->ry=128;
    uint64_t now=sceKernelGetProcessTimeWide();
    float elapsed=(now-previous_time)/1000000.0f;
    previous_time=now;
    out->resumed=elapsed>0.25f;
    // Discard long gaps after suspend/LiveArea; never advance physics through them.
    out->dt=out->resumed?0:clampf(elapsed,0,0.05f);
    if(out->resumed) { previous_buttons=0; start_sensors(); }
    if(elapsed>0 && elapsed<0.25f) { frame_accumulator+=elapsed; frames++; }
    if(frame_accumulator>=0.5f) { measured_fps=frames/frame_accumulator; frames=0; frame_accumulator=0; }
    out->fps=measured_fps;
    SceCtrlData pad={0};
    out->ctrl_result=sceCtrlPeekBufferPositive(0,&pad,1);
    if(out->ctrl_result>0) {
        out->buttons=pad.buttons; out->lx=pad.lx; out->ly=pad.ly; out->rx=pad.rx; out->ry=pad.ry;
    }
    out->pressed=out->buttons & ~previous_buttons;
    previous_buttons=out->buttons;
    poll_touch(0,&out->front); poll_touch(1,&out->back);
    SceMotionState motion={0};
    out->motion_start_result=motion_start;
    out->motion_result=sceMotionGetState(&motion);
    if(out->motion_result>=0) {
        motion_sampling=true;
        out->acceleration=(Vec3){motion.acceleration.x,motion.acceleration.y,motion.acceleration.z};
        out->gyro=(Vec3){motion.angularVelocity.x,motion.angularVelocity.y,motion.angularVelocity.z};
    }
}
void platform_begin(void) { vita2d_start_drawing(); vita2d_clear_screen(); }
void platform_end(void) { vita2d_end_drawing(); vita2d_swap_buffers(); }
bool platform_should_exit(void) { return false; }
void platform_shutdown(void) {
    sceTouchSetSamplingState(0,SCE_TOUCH_SAMPLING_STATE_STOP);
    sceTouchSetSamplingState(1,SCE_TOUCH_SAMPLING_STATE_STOP);
    if(motion_sampling) sceMotionStopSampling();
    vita2d_wait_rendering_done();
    vita2d_free_pgf(font); font=NULL;
    vita2d_fini();
    sceKernelExitProcess(0);
}
void draw_rect(float x,float y,float w,float h,uint32_t c) { vita2d_draw_rectangle(x,y,w,h,c); }
void draw_circle(float x,float y,float r,uint32_t c) { vita2d_draw_fill_circle(x,y,r,c); }
void draw_line(float x,float y,float x2,float y2,uint32_t c) { vita2d_draw_line(x,y,x2,y2,c); }
void draw_text(float x,float y,float scale,uint32_t c,const char *t) { vita2d_pgf_draw_text(font,(int)x,(int)y,c,scale,t); }
