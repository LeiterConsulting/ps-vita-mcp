#include "lab_core.h"
#include "lab_platform.h"
#include "lab_server.h"
#include <psp2/ctrl.h>
#include <psp2/kernel/processmgr.h>
#include <vita2d.h>
#include <stdio.h>

/* Installer/runtime provenance marker. This source is compiled independently
   from DevLoop, Resident and Control and contains no authentication material. */
const char lab_native_identity[]="VITA_NATIVE_LIFECYCLE_LAB:" LAB_BUILD_ID;
int main(void){
    unsigned char nonce[16]={0};LabCore core;
    if(!lp_nonce(nonce)||!lab_init(&core,lp_pid(),nonce))return 1;
    vita2d_init();vita2d_set_clear_color(RGBA8(12,21,35,255));
    vita2d_pgf *font=vita2d_load_default_pgf();
    if(!font){vita2d_fini();return 1;}
    int network=lab_server_start(&core)==0;
    while(!lab_exit_ready(&core)){
        SceCtrlData pad={0};sceCtrlPeekBufferPositive(0,&pad,1);
        if((pad.buttons&(SCE_CTRL_START|SCE_CTRL_SELECT))==(SCE_CTRL_START|SCE_CTRL_SELECT))break;
        lab_tick(&core,lp_now());if(network)lab_server_tick(&core);
        vita2d_start_drawing();vita2d_clear_screen();
        unsigned accent=LAB_VARIANT==1?RGBA8(57,221,195,255):RGBA8(251,198,76,255);
        vita2d_draw_rectangle(24,28,912,5,accent);
        vita2d_pgf_draw_text(font,28,87,accent,1.1f,"Vita Lifecycle Lab");
        char line[200];snprintf(line,sizeof(line),"Version %s   Variant %u   PAUSED",LAB_VERSION,(unsigned)LAB_VARIANT);
        vita2d_pgf_draw_text(font,28,126,RGBA8(225,234,244,255),0.85f,line);
        snprintf(line,sizeof(line),"Native self-test: %s   CRC32 %08x",core.selftest_passed?"PASS":"FAIL",core.checksum);
        vita2d_pgf_draw_text(font,28,177,accent,0.85f,line);
        snprintf(line,sizeof(line),"PID %d   Frame %llu   Revision %u",(int)core.pid,(unsigned long long)core.frame,core.revision);
        vita2d_pgf_draw_text(font,28,220,RGBA8(169,189,209,255),0.8f,line);
        snprintf(line,sizeof(line),"Build %.24s",LAB_BUILD_ID);
        vita2d_pgf_draw_text(font,28,263,RGBA8(169,189,209,255),0.8f,line);
        vita2d_draw_fill_circle(48+(float)(core.frame%850),330,12,accent);
        vita2d_pgf_draw_text(font,28,430,network?accent:RGBA8(255,101,111,255),0.8f,
            network?"Authenticated status and cooperative exit on port 17868":"Network unavailable: Resident pairing file or network initialization failed");
        vita2d_pgf_draw_text(font,28,489,RGBA8(169,189,209,255),0.75f,"MCP owns the development cycle. START + SELECT exits manually.");
        vita2d_end_drawing();vita2d_swap_buffers();
    }
    int stop=network?lab_server_stop():0;
    vita2d_wait_rendering_done();vita2d_free_pgf(font);vita2d_fini();
    sceKernelExitProcess(stop<0?1:0);return 0;
}
