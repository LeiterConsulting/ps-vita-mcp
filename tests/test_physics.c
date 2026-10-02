#include "physics.h"
#include "math_helpers.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static void bounds(const World *w) {
    assert(isfinite(w->x)&&isfinite(w->y)&&isfinite(w->vx)&&isfinite(w->vy));
    assert(w->x>=w->left+w->radius-0.001f&&w->x<=w->right-w->radius+0.001f);
    assert(w->y>=w->top+w->radius-0.001f&&w->y<=w->bottom-w->radius+0.001f);
}
int main(void) {
    World w;
    assert(axis_raw(0)==-1&&axis_raw(128)==0&&axis_raw(255)==1);
    assert(axis_deadzone(139,0.12f)==0&&axis_deadzone(255,0.12f)==1);
    assert(normalize_touch(108,108,1919)==0&&normalize_touch(1919,108,1919)==1);
    assert(normalize_touch(-100,108,1919)==0&&normalize_touch(9999,108,1919)==1);
    assert(normalize_touch(2,1,1)==0.5f);
    puts("PASS analog endpoints, deadzone and panel coordinate bounds");
    world_init(&w); float x=w.x,y=w.y;
    world_step(&w,10,1,1,false); assert(w.x==x&&w.y==y);
    world_step(&w,NAN,1,1,false); assert(w.x==x&&w.y==y);
    world_step(&w,0,1,1,false); assert(w.x==x&&w.y==y);
    puts("PASS suspend gaps and invalid time do not advance the ball");
    world_init(&w); w.x=260; w.y=230; w.vx=340;
    world_step(&w,0.2f,1,0,false); assert(w.x<=300-w.radius+0.001f); assert(w.vx<0);
    w.x=310; w.y=240; w.vx=w.vy=0; world_step(&w,1.0f/120,0,0,false);
    assert(w.x<=300-w.radius+0.001f || w.x>=326+w.radius-0.001f);
    puts("PASS fast-ball wall collision and recovery from overlap");
    world_init(&w); assert(!world_add_obstacle(&w,w.x,w.y));
    assert(!world_add_obstacle(&w,w.goal_x,w.goal_y));
    assert(!world_add_obstacle(&w,106,418));
    w.x=200; w.y=380; assert(!world_add_obstacle(&w,106,285));
    assert(world_add_obstacle(&w,410,170)); assert(!world_add_obstacle(&w,410,170));
    world_clear_added(&w); assert(w.obstacle_count==3);
    puts("PASS obstacle placement protects ball, future targets and other obstacles");
    world_init(&w); w.x=w.goal_x; w.y=w.goal_y;
    world_step(&w,1.0f/120,0,0,false); assert(w.score==1&&w.x==106&&w.y==285&&w.goal_y==418);
    world_step(&w,1.0f/120,0,0,false); assert(w.score==1);
    puts("PASS goal scores once, relocates and respawns the ball");
    World free_w,brake_w; world_init(&free_w); free_w.vx=150; brake_w=free_w;
    world_step(&free_w,0.1f,0,0,false); world_step(&brake_w,0.1f,0,0,true);
    assert(fabsf(brake_w.vx)<fabsf(free_w.vx));
    puts("PASS rear-touch brake increases damping");
    float fx,fy; tilt_force(0,0,-1,0,0,-1,&fx,&fy); assert(fx==0&&fy==0);
    tilt_force(0.2f,0.2f,-1,0,0,-1,&fx,&fy); assert(fx>0&&fy<0);
    tilt_force(0,1,0.2f,0,1,0,&fx,&fy); assert(fy<0);
    tilt_force(NAN,0,-1,0,0,-1,&fx,&fy); assert(isfinite(fx)&&isfinite(fy));
    puts("PASS neutral calibration adapts to flat and upright poses");
    world_init(&w);
    for(int n=0;n<100000;n++) {
        float angle=n*0.013f; world_step(&w,1.0f/120,cosf(angle),sinf(angle),n%500<20); bounds(&w);
    }
    puts("PASS 100000-step deterministic stress stays finite and in bounds");
    puts("8 host test groups passed; physical Vita testing remains separate.");
    return 0;
}
