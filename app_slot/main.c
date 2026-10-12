#include "app_api.h"
#include "app_slot_config.h"
#include "lab_core.h"
#include "lab_platform.h"
#include "lab_server.h"
#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <stdio.h>

/* Deliberately retain the qualified install/runtime identity for one owned
   development slot. This is not an arbitrary application-title adapter. */
const char lab_native_identity[]="VITA_NATIVE_LIFECYCLE_LAB:" LAB_BUILD_ID;
int main(void) {
    unsigned char nonce[16]={0};LabCore core;
    if(!lp_nonce(nonce)||!lab_init(&core,lp_pid(),nonce))return 1;
    vita2d_init();vita2d_set_clear_color(RGBA8(12,21,35,255));
    vita2d_pgf *font=vita2d_load_default_pgf();
    if(!font){vita2d_fini();return 1;}
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG_WIDE);
    int initialized=app_init();
    int application_passed=initialized&&app_selftest();
    /* CRC remains an independent harness check. Aggregate failure is visible
       through the unchanged authenticated Lab status/cleanup contract. */
    core.selftest_passed=core.selftest_passed&&application_passed;
    int network=lab_server_start(&core)==0;
    uint64_t previous=lp_now();uint32_t held=0;
    while(!lab_exit_ready(&core)) {
        SceCtrlData pad={0};pad.lx=pad.ly=pad.rx=pad.ry=128;
        int read=sceCtrlPeekBufferPositive(0,&pad,1);
        if((pad.buttons&(SCE_CTRL_START|SCE_CTRL_SELECT))==(SCE_CTRL_START|SCE_CTRL_SELECT))break;
        uint64_t now=lp_now();float dt=now>=previous?(float)(now-previous)/1000.0f:0.0f;
        previous=now;if(dt>0.05f)dt=0.05f;
        AppSlotInput input={dt,pad.buttons,pad.buttons&~held,pad.lx,pad.ly,pad.rx,pad.ry,read};
        held=pad.buttons;
        if(initialized&&application_passed&&!app_update(&input)){
            application_passed=0;core.selftest_passed=0;
        }
        lab_tick(&core,now);if(network)lab_server_tick(&core);
        vita2d_start_drawing();vita2d_clear_screen();
        if(initialized)app_draw(font);
        unsigned accent=core.selftest_passed?RGBA8(57,221,195,255):RGBA8(255,101,111,255);
        vita2d_draw_rectangle(24,26,912,4,accent);
        vita2d_pgf_draw_text(font,28,67,accent,0.85f,APP_SLOT_NAME " - native prototype");
        char line[160];
        snprintf(line,sizeof(line),"App self-test %s | Harness CRC %08x | Frame %llu",
                 application_passed?"PASS":"FAIL",core.checksum,(unsigned long long)core.frame);
        vita2d_pgf_draw_text(font,28,103,accent,0.65f,line);
        snprintf(line,sizeof(line),"%s | %.16s | PID %d",LAB_VERSION,LAB_BUILD_ID,(int)core.pid);
        vita2d_pgf_draw_text(font,28,490,RGBA8(169,189,209,255),0.6f,line);
        vita2d_pgf_draw_text(font,28,523,network?accent:RGBA8(255,101,111,255),0.6f,
            network?"Single development slot VMCP00001 | START + SELECT exits":"Network unavailable | START + SELECT exits");
        vita2d_end_drawing();vita2d_swap_buffers();
    }
    int stop=network?lab_server_stop():0;
    if(initialized)app_cleanup();
    vita2d_wait_rendering_done();vita2d_free_pgf(font);vita2d_fini();
    sceKernelExitProcess(stop<0?1:0);return 0;
}
