#include "app_sim.h"
#include <math.h>

static float clamp(float value,float low,float high){return value<low?low:value>high?high:value;}
void app_sim_init(AppSimulation *s){*s=(AppSimulation){480,280,220,90,280,0,0,0};}
int app_sim_valid(const AppSimulation *s){
    return s&&isfinite(s->x)&&isfinite(s->y)&&isfinite(s->vx)&&isfinite(s->vy)
        &&isfinite(s->paddle_y)&&isfinite(s->elapsed)&&s->x>=40&&s->x<=920
        &&s->y>=160&&s->y<=440&&s->paddle_y>=196&&s->paddle_y<=404&&s->elapsed>=0;
}
void app_sim_step(AppSimulation *s,float dt,float direction){
    if(!app_sim_valid(s)||!isfinite(dt)||!isfinite(direction)||dt<=0||dt>0.05f)return;
    s->paddle_y=clamp(s->paddle_y+clamp(direction,-1,1)*320*dt,196,404);
    float previous=s->x;s->x+=s->vx*dt;s->y+=s->vy*dt;s->elapsed+=dt;
    if(s->y<160){s->y=160;s->vy=fabsf(s->vy);}
    if(s->y>440){s->y=440;s->vy=-fabsf(s->vy);}
    if(s->x>920){s->x=920;s->vx=-fabsf(s->vx);}
    if(s->vx<0&&previous>=92&&s->x<=92&&fabsf(s->y-s->paddle_y)<=43){
        s->x=92;s->vx=fabsf(s->vx);s->hits++;
    }
    if(s->x<40){s->misses++;s->x=480;s->y=280;s->vx=fabsf(s->vx);s->vy=90;}
}
int app_sim_selftest(void){
    AppSimulation s;app_sim_init(&s);if(!app_sim_valid(&s))return 0;
    app_sim_step(&s,0.05f,1);if(s.x<=480||s.paddle_y<=280||s.elapsed<=0)return 0;
    s.y=160;s.vy=-100;app_sim_step(&s,0.01f,0);if(s.y!=160||s.vy<=0)return 0;
    s.y=440;s.vy=100;app_sim_step(&s,0.01f,0);if(s.y!=440||s.vy>=0)return 0;
    s.x=920;s.vx=100;app_sim_step(&s,0.01f,0);if(s.x!=920||s.vx>=0)return 0;
    s.x=93;s.y=s.paddle_y;s.vx=-200;s.vy=0;app_sim_step(&s,0.01f,0);
    if(s.x!=92||s.vx<=0||s.hits!=1)return 0;
    s.x=40;s.y=160;s.paddle_y=404;s.vx=-200;app_sim_step(&s,0.01f,0);
    if(s.misses!=1||s.x!=480||s.vx<=0)return 0;
    for(unsigned n=0;n<2000;n++)app_sim_step(&s,0.01f,n&1?1:-1);
    return app_sim_valid(&s);
}
