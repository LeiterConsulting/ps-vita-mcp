#ifndef WORKBENCH_TELEMETRY_H
#define WORKBENCH_TELEMETRY_H
#include "platform.h"
typedef struct {
    uint64_t frame,sampled_ms,resumes,active_frames,neutral_frames;
    uint32_t buttons_seen,last_buttons;
    unsigned char last_sticks[4];
    int front_seen,rear_seen,front_x,front_y,rear_x,rear_y;
    Input input;
} TargetState;
void target_sample(TargetState *state,const Input *input,uint64_t sampled_ms);
int target_json(const TargetState *state,char *out,unsigned capacity,int pid,const char *run,const char *build);
int target_server_start(void);
void target_server_publish(const TargetState *state);
void target_server_stop(void);
int target_server_health(void);
#endif
