#ifndef VITA_SLOT_SIMULATION_H
#define VITA_SLOT_SIMULATION_H
typedef struct {
    float x,y,vx,vy,paddle_y,elapsed;
    unsigned hits,misses;
} AppSimulation;
void app_sim_init(AppSimulation *state);
int app_sim_valid(const AppSimulation *state);
void app_sim_step(AppSimulation *state,float dt,float paddle_direction);
int app_sim_selftest(void);
#endif
