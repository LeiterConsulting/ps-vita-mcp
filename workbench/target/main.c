#include "telemetry.h"
#include <psp2/kernel/processmgr.h>
#include <stdio.h>
int main(void) {
    if(!platform_init()) return 1;
    int network=target_server_start(); TargetState state={0};
    for(;;) {
        Input input;platform_poll(&input);target_sample(&state,&input,sceKernelGetProcessTimeWide()/1000);target_server_publish(&state);
        if((input.buttons&(BTN_START|BTN_SELECT))==(BTN_START|BTN_SELECT)) break;
        platform_begin();
        draw_text(36,60,1.4f,COLOR(64,220,191),"VITA INPUT TARGET 01.00");
        draw_text(36,104,1.0f,COLOR(220,232,244),"Quiet input, expiry and focus test. START + SELECT exits.");
        char line[192];
        snprintf(line,sizeof(line),"Read-only telemetry :17868 | setup %d | server %d",network,target_server_health());draw_text(36,160,1,COLOR(220,232,244),line);
        snprintf(line,sizeof(line),"Frame %llu | buttons %08x | seen %08x | %.1f fps",(unsigned long long)state.frame,input.buttons,state.buttons_seen,input.fps);draw_text(36,214,1,COLOR(220,232,244),line);
        snprintf(line,sizeof(line),"Sticks: %u %u / %u %u",input.lx,input.ly,input.rx,input.ry);draw_text(36,258,1,COLOR(220,232,244),line);
        snprintf(line,sizeof(line),"Synthetic touch frames: front %d at %d,%d | rear %d at %d,%d",state.front_seen,state.front_x,state.front_y,state.rear_seen,state.rear_x,state.rear_y);draw_text(36,302,1,COLOR(220,232,244),line);
        snprintf(line,sizeof(line),"Active %llu | neutral after input %llu | resumes %llu",(unsigned long long)state.active_frames,(unsigned long long)state.neutral_frames,(unsigned long long)state.resumes);draw_text(36,346,1,COLOR(220,232,244),line);
        draw_circle(300+(input.lx-128)*.7f,435+(input.ly-128)*.5f,8,COLOR(64,220,191));
        draw_circle(650+(input.rx-128)*.7f,435+(input.ry-128)*.5f,8,COLOR(220,180,64));
        platform_end();
    }
    target_server_stop(); platform_shutdown();return 0;
}
