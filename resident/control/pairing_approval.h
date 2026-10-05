#ifndef VITA_PAIRING_APPROVAL_H
#define VITA_PAIRING_APPROVAL_H
#include <stdint.h>
typedef struct {uint64_t neutral_since;int neutral;} PAArm;
/* Drain earlier foreground/controller samples before accepting a new CROSS edge. */
static inline int pa_cross(PAArm *a,uint64_t now,int pending,int valid,uint32_t held,uint32_t pressed,uint32_t cross) {
    if(!pending||!valid){a->neutral=0;return 0;}
    if(!held){if(!a->neutral||now<a->neutral_since){a->neutral=1;a->neutral_since=now;}return 0;}
    int approved=a->neutral&&now>=a->neutral_since&&now-a->neutral_since>=500&&held==cross&&(pressed&cross);
    a->neutral=0;return approved;
}
#endif
