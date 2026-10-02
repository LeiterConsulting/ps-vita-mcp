#ifndef DEVLOOP_SCRIPT_RUNTIME_H
#define DEVLOOP_SCRIPT_RUNTIME_H
#include "platform.h"
#include <stddef.h>
#define SCRIPT_MAX 16384
#define SCRIPT_MEMORY_MAX (1024*1024)
#define SCRIPT_DRAW_MAX 256
typedef struct { char name[25]; float value; } DevMetric;
typedef struct {
    bool loaded,active,faulted,rollback_available;
    char name[33],sha256[65],previous_name[33],previous_sha256[65],error[256];
    unsigned source_bytes,updates,draw_commands,memory_bytes,peak_memory_bytes;
    float update_ms,draw_ms;
    unsigned metric_count; DevMetric metrics[8];
} DevScriptInfo;
void script_shutdown(void);
bool script_load(const char *name,const char *source,const char *sha256,const Input *input,char *error,size_t capacity);
bool script_control(const char *action,const Input *input,char *error,size_t capacity);
bool script_frame(const Input *input,bool paused);
void script_render(void);
void script_info(DevScriptInfo *out);
unsigned script_take_logs(char out[8][128]);
#endif
