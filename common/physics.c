#include "physics.h"
#include "math_helpers.h"
#include <math.h>
#include <string.h>

static void choose_goal(World *w) {
    const float xs[]={854,854,106,106},ys[]={160,418,418,160};
    w->goal_x=xs[w->score%4]; w->goal_y=ys[w->score%4];
}
void world_reset_ball(World *w) { w->x=106; w->y=285; w->vx=w->vy=0; }
void world_init(World *w) {
    memset(w,0,sizeof(*w)); w->radius=13;
    w->left=30; w->top=94; w->right=930; w->bottom=474; w->goal_radius=25;
    w->obstacles[0]=(Obstacle){300,170,26,150};
    w->obstacles[1]=(Obstacle){480,290,165,26};
    w->obstacles[2]=(Obstacle){725,125,26,150};
    w->obstacle_count=3; choose_goal(w); world_reset_ball(w);
}
void world_clear_added(World *w) { w->obstacle_count=3; }
static bool overlap(const Obstacle *a,const Obstacle *b) {
    return a->x<b->x+b->w+8 && a->x+a->w+8>b->x && a->y<b->y+b->h+8 && a->y+a->h+8>b->y;
}
bool world_add_obstacle(World *w,float x,float y) {
    if(w->obstacle_count>=MAX_OBSTACLES || !isfinite(x)||!isfinite(y)) return false;
    Obstacle o={clampf(x-30,w->left+6,w->right-66),clampf(y-14,w->top+6,w->bottom-34),60,28};
    Obstacle ball={w->x-w->radius-10,w->y-w->radius-10,2*w->radius+20,2*w->radius+20};
    Obstacle spawn={106-w->radius-10,285-w->radius-10,2*w->radius+20,2*w->radius+20};
    // Reserve every goal location, including goals reached later in the session.
    const float xs[]={854,854,106,106},ys[]={160,418,418,160};
    if(overlap(&o,&ball)) return false;
    if(overlap(&o,&spawn)) return false;
    for(int n=0;n<4;n++) {
        Obstacle goal={xs[n]-w->goal_radius,ys[n]-w->goal_radius,2*w->goal_radius,2*w->goal_radius};
        if(overlap(&o,&goal)) return false;
    }
    for(int n=0;n<w->obstacle_count;n++) if(overlap(&o,&w->obstacles[n])) return false;
    w->obstacles[w->obstacle_count++]=o; return true;
}
static void collide_obstacle(World *w,const Obstacle *o) {
    float cx=clampf(w->x,o->x,o->x+o->w),cy=clampf(w->y,o->y,o->y+o->h);
    float dx=w->x-cx,dy=w->y-cy,d2=dx*dx+dy*dy;
    if(d2>=w->radius*w->radius) return;
    float nx,ny,penetration;
    if(d2>0.0001f) {
        float d=sqrtf(d2); nx=dx/d; ny=dy/d; penetration=w->radius-d;
    } else {
        // Resolve a ball exactly inside an obstacle instead of dividing by zero.
        float distances[]={w->x-o->x,o->x+o->w-w->x,w->y-o->y,o->y+o->h-w->y};
        int side=0; for(int n=1;n<4;n++) if(distances[n]<distances[side]) side=n;
        nx=side==0?-1:(side==1?1:0); ny=side==2?-1:(side==3?1:0);
        penetration=w->radius+distances[side];
    }
    w->x+=nx*(penetration+0.01f); w->y+=ny*(penetration+0.01f);
    float incoming=w->vx*nx+w->vy*ny;
    if(incoming<0) { w->vx-=1.65f*incoming*nx; w->vy-=1.65f*incoming*ny; }
}
PhysicsParams physics_defaults(void) { return (PhysicsParams){620,0.9f,10,340}; }
static void substep(World *w,float dt,float fx,float fy,bool brake,const PhysicsParams *p) {
    float damping=expf(-(brake?p->brake:p->drag)*dt);
    w->vx=(w->vx+clampf(fx,-1,1)*p->gravity*dt)*damping;
    w->vy=(w->vy+clampf(fy,-1,1)*p->gravity*dt)*damping;
    float speed=sqrtf(w->vx*w->vx+w->vy*w->vy);
    if(speed>p->max_speed) { w->vx*=p->max_speed/speed; w->vy*=p->max_speed/speed; }
    w->x+=w->vx*dt; w->y+=w->vy*dt;
    for(int pass=0;pass<2;pass++) for(int n=0;n<w->obstacle_count;n++) collide_obstacle(w,&w->obstacles[n]);
    if(w->x<w->left+w->radius) { w->x=w->left+w->radius; w->vx=fabsf(w->vx)*0.65f; }
    if(w->x>w->right-w->radius) { w->x=w->right-w->radius; w->vx=-fabsf(w->vx)*0.65f; }
    if(w->y<w->top+w->radius) { w->y=w->top+w->radius; w->vy=fabsf(w->vy)*0.65f; }
    if(w->y>w->bottom-w->radius) { w->y=w->bottom-w->radius; w->vy=-fabsf(w->vy)*0.65f; }
    float dx=w->x-w->goal_x,dy=w->y-w->goal_y;
    if(dx*dx+dy*dy<(w->goal_radius-w->radius*0.25f)*(w->goal_radius-w->radius*0.25f)) {
        w->score++; choose_goal(w); world_reset_ball(w);
    }
}
void world_step(World *w,float dt,float fx,float fy,bool brake) {
    PhysicsParams defaults=physics_defaults();
    world_step_configured(w,dt,fx,fy,brake,&defaults);
}
void world_step_configured(World *w,float dt,float fx,float fy,bool brake,const PhysicsParams *p) {
    if(!isfinite(dt)||dt<=0 || dt>0.25f) return;
    if(!isfinite(fx)) fx=0;
    if(!isfinite(fy)) fy=0;
    // Bound movement per substep so a fast ball cannot jump through a thin wall.
    while(dt>0.00001f) { float step=fminf(dt,1.0f/120); substep(w,step,fx,fy,brake,p); dt-=step; }
}
void tilt_force(float ax,float ay,float az,float nx,float ny,float nz,float *fx,float *fy) {
    // Use the gravity tangent at the captured neutral pose. This adapts to a
    // console held flat or upright; basicOrientation is deliberately not used.
    float yz=sqrtf(ny*ny+nz*nz),ty=1,tz=0;
    if(yz>0.1f) { ty=-nz/yz; tz=ny/yz; }
    *fx=clampf((ax-nx)*2.4f,-1,1);
    *fy=clampf(-((ay-ny)*ty+(az-nz)*tz)*2.4f,-1,1);
    if(!isfinite(*fx)) *fx=0;
    if(!isfinite(*fy)) *fy=0;
}
