#ifndef VITA_LAB_PHYSICS_H
#define VITA_LAB_PHYSICS_H
#include <stdbool.h>
#define MAX_OBSTACLES 19
typedef struct { float x,y,w,h; } Obstacle;
typedef struct {
    float x,y,vx,vy,radius;
    float left,top,right,bottom;
    float goal_x,goal_y,goal_radius;
    Obstacle obstacles[MAX_OBSTACLES];
    int obstacle_count,score;
} World;
typedef struct { float gravity,drag,brake,max_speed; } PhysicsParams;
PhysicsParams physics_defaults(void);
void world_step_configured(World *world,float dt,float force_x,float force_y,bool brake,const PhysicsParams *params);
void world_init(World *world);
void world_reset_ball(World *world);
void world_clear_added(World *world);
bool world_add_obstacle(World *world,float x,float y);
void world_step(World *world,float dt,float force_x,float force_y,bool brake);
void tilt_force(float ax,float ay,float az,float nx,float ny,float nz,float *out_x,float *out_y);
#endif
