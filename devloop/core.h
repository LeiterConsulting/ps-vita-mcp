#ifndef DEVLOOP_CORE_H
#define DEVLOOP_CORE_H
#include "platform.h"
#include "physics.h"
#include "script_runtime.h"
#include <stddef.h>
#include <stdint.h>
#define DEV_PORT 17865
#define DEV_VERSION "01.03"
#define DEV_JSON_MAX 8192
typedef struct {
    World world; PhysicsParams params; Input input;
    bool paused,stick_only,neutral_valid,invert_x,invert_y;
    Vec3 neutral,filtered;
    float accumulator,force_x,force_y;
    uint32_t revision;
    uint64_t frame,sampled_ms;
    unsigned old_ids[MAX_TOUCHES]; int old_count;
    char logs[12][128]; unsigned log_sequence;
    DevScriptInfo script;
} DevCore;
typedef struct {
    bool parameters;
    uint32_t expected_revision;
    PhysicsParams params;
    unsigned mask;
    char action[24];
    bool script_upload;
    char script_name[33],script_sha256[65],script_source[SCRIPT_MAX+1];
} DevCommand;
void dev_init(DevCore *core);
void dev_tick(DevCore *core,const Input *input,uint64_t sampled_ms);
int dev_parse_command(const char *path,const char *body,DevCommand *command,char *error,size_t capacity);
int dev_apply(DevCore *core,const DevCommand *command,char *error,size_t capacity);
void dev_status_json(const DevCore *core,char *out,size_t capacity);
void dev_input_json(const DevCore *core,char *out,size_t capacity);
void dev_logs_json(const DevCore *core,char *out,size_t capacity);
void dev_script_json(const DevCore *core,char *out,size_t capacity);
void dev_error_json(char *out,size_t capacity,const char *message);
void dev_log(DevCore *core,const char *message);
#endif
