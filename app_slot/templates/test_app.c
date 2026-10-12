#include "app_sim.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void){
    AppSimulation s,original,twin;app_sim_init(&s);original=s;
    assert(app_sim_valid(&s));assert(app_sim_selftest());
    app_sim_step(&s,0,1);assert(memcmp(&s,&original,sizeof(s))==0);
    app_sim_step(&s,NAN,1);assert(memcmp(&s,&original,sizeof(s))==0);
    app_sim_step(&s,0.1f,1);assert(memcmp(&s,&original,sizeof(s))==0);
    app_sim_step(&s,0.01f,NAN);assert(memcmp(&s,&original,sizeof(s))==0);
    app_sim_step(&s,0.05f,0);assert(fabsf(s.x-491)<0.001f);assert(fabsf(s.y-284.5f)<0.001f);
    s.y=160;s.vy=-90;app_sim_step(&s,0.01f,0);assert(s.y==160&&s.vy==90);
    s.y=440;s.vy=90;app_sim_step(&s,0.01f,0);assert(s.y==440&&s.vy==-90);
    s.x=920;s.vx=220;app_sim_step(&s,0.01f,0);assert(s.x==920&&s.vx==-220);
    s.x=93;s.y=s.paddle_y;s.vx=-220;s.vy=0;app_sim_step(&s,0.01f,0);assert(s.hits==1&&s.x==92&&s.vx==220);
    s.x=40;s.y=160;s.paddle_y=404;s.vx=-220;app_sim_step(&s,0.01f,0);assert(s.misses==1&&s.x==480&&s.y==280);
    for(unsigned n=0;n<100;n++){app_sim_step(&s,0.05f,1);}
    assert(s.paddle_y==404);
    for(unsigned n=0;n<100;n++){app_sim_step(&s,0.05f,-1);}
    assert(s.paddle_y==196);
    app_sim_init(&s);twin=s;
    for(unsigned n=0;n<10000;n++){
        float direction=(n%200)<100?1:-1;app_sim_step(&s,0.01f,direction);app_sim_step(&twin,0.01f,direction);
        assert(app_sim_valid(&s));assert(memcmp(&s,&twin,sizeof(s))==0);
    }
    assert(s.hits+s.misses>0);s.x=NAN;assert(!app_sim_valid(&s));
    puts("Native-slot application tests passed: 10000 paired deterministic steps plus collision, bounds and reset checks; no physical input claims.");return 0;
}
