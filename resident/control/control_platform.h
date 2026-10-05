#ifndef VITA_CONTROL_PLATFORM_H
#define VITA_CONTROL_PLATFORM_H
#include "../platform.h"
#include "api.h"
#include "power_policy.h"
#undef R_PORT
#define R_PORT 17867
#define RC_MAX_FRAME (480u*272u*3u)
typedef struct { char name[64]; uint64_t bytes; int directory; } RCEntry;
int rc_list(const char *path,unsigned offset,RCEntry entries[32],int *more);
int rc_remove(const char *path);
int rc_input(const RInput *input);
int rc_readback(RReadback *state);
int rc_release(void);
int rc_capture(unsigned char *pixels,RFrame *frame,unsigned scale);
int rc_app(int launch,const char *title);
int rp_set(const RPConfig *config);
int rp_read(RPState *state);
int rp_start(void);
int rp_stop(void);
#endif
