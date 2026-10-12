#include "app.h"
#include "app_sim.h"
#include <psp2/ctrl.h>
#include <stdio.h>

static AppSimulation state;
int app_init(void){app_sim_init(&state);return 1;}
int app_selftest(void){return app_sim_selftest();}
int app_update(const AppSlotInput *input){
    float direction=((float)input->ly-128)/127;
    if(direction>-0.15f&&direction<0.15f)direction=0;
    if(input->buttons&SCE_CTRL_UP)direction=-1;
    if(input->buttons&SCE_CTRL_DOWN)direction=1;
    if(input->pressed&SCE_CTRL_CROSS)app_sim_init(&state);
    app_sim_step(&state,input->dt,direction);
    return app_sim_valid(&state);
}
void app_draw(vita2d_pgf *font){
    unsigned white=RGBA8(225,234,244,255),gold=RGBA8(251,198,76,255),teal=RGBA8(57,221,195,255);
    vita2d_draw_rectangle(40,160,880,280,RGBA8(20,32,49,255));
    vita2d_draw_rectangle(80,state.paddle_y-36,12,72,teal);
    vita2d_draw_rectangle(919,160,2,280,white);
    vita2d_draw_fill_circle(state.x,state.y,7,gold);
    char line[120];snprintf(line,sizeof(line),"Paddle prototype | Hits %u | Misses %u",state.hits,state.misses);
    vita2d_pgf_draw_text(font,40,142,white,0.72f,line);
    vita2d_pgf_draw_text(font,40,466,white,0.65f,"Left stick / UP / DOWN move | CROSS resets | Physical input acceptance pending");
}
void app_cleanup(void){}
