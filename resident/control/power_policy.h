#ifndef VITA_WORK_POWER_POLICY_H
#define VITA_WORK_POWER_POLICY_H
#include <stdint.h>
#include "api.h"
#define RP_MAGIC 0x31505756u
typedef struct { uint32_t magic,abi,ttl_ms,idle_ms,dim_percent; } RPConfig;
typedef struct {
    uint64_t expires_ms,last_activity_ms,last_tick_ms;
    uint32_t idle_ms,dim_percent,activity_flags;
    int dimmed,original,applied,current,motion_result,motion_valid,tick_result,brightness_result;
    int touch_result,touch_pid;
    uint32_t touch_panels;
    uint64_t touch_sample_ms;
    RTouchPanel touch_diagnostics[2];
} RPState;
typedef struct { int keep_awake,brightness; } RPAction;
int rp_valid(const RPConfig *config);
void rp_lease(RPState *state,const RPConfig *config,uint64_t now_ms);
RPAction rp_step(RPState *state,uint64_t now_ms,int network_ready,int current_brightness,uint32_t activity,int motion_valid);
void rp_applied(RPState *state,int brightness,int result);
int rp_motion(float acceleration[3],float gyro[3],float baseline[3],int *initialized,int *consecutive);
#endif
