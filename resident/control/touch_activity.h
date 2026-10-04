#ifndef VITA_CONTROL_TOUCH_ACTIVITY_H
#define VITA_CONTROL_TOUCH_ACTIVITY_H
#include <stdint.h>
#define RT_READERS 4
typedef struct {
    int32_t pid; uint32_t count,reads,advances;
    uint64_t source_ticks,received_ms,changed_ms;
} RTEvent;
typedef struct {
    RTEvent panel[2][RT_READERS];
    int32_t last_pid[2]; uint32_t reads[2];
} RTState;
/* A real hardware contact can also have ID 112. Only a matching active
   synthetic point can be excluded; never exclude the ID by itself. */
static inline int rt_synthetic(uint32_t id,int x,int y,int active,uint32_t synthetic_id,int sx,int sy) {
    return active&&id==synthetic_id&&x==sx&&y==sy;
}
static inline const RTEvent *rt_reader(const RTState *s,unsigned panel,int32_t pid) {
    if(panel>1||pid<=0) return 0;
    for(unsigned i=0;i<RT_READERS;i++) if(s->panel[panel][i].pid==pid) return &s->panel[panel][i];
    return 0;
}
/* Source ticks have no assumed relationship to the kernel clock. Freshness
   uses receipt time only when that reader's source timestamp advances. Empty
   samples release contacts; repeated buffered samples cannot prolong activity.
   Separate bounded reader slots prevent Shell reads erasing app observations. */
static inline void rt_observe(RTState *s,unsigned panel,int32_t pid,uint32_t count,uint64_t ticks,uint64_t now) {
    if(panel>1||pid<=0||count>8) return;
    RTEvent *e=0,*oldest=&s->panel[panel][0];
    for(unsigned i=0;i<RT_READERS;i++) {
        RTEvent *candidate=&s->panel[panel][i];
        if(candidate->pid==pid) { e=candidate;break; }
        if(!candidate->pid||candidate->received_ms<oldest->received_ms) oldest=candidate;
    }
    if(!e) { e=oldest;*e=(RTEvent){.pid=pid}; }
    s->last_pid[panel]=pid;s->reads[panel]++;e->reads++;e->received_ms=now;
    if(ticks&&ticks>e->source_ticks) {
        e->source_ticks=ticks;e->changed_ms=now;e->count=count;e->advances++;
    }
}
static inline uint32_t rt_panels(const RTState *s,int32_t foreground,uint64_t now) {
    uint32_t result=0;
    if(foreground<=0) return 0;
    for(unsigned p=0;p<2;p++) {
        const RTEvent *e=rt_reader(s,p,foreground);
        if(e&&e->count&&e->source_ticks&&now>=e->changed_ms&&now-e->changed_ms<=250) result|=1u<<p;
    }
    return result;
}
#endif
