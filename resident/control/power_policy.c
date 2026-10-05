#include "power_policy.h"
#include "api.h"
int rp_valid(const RPConfig *c) {
    return c&&c->magic==RP_MAGIC&&c->abi==RC_ABI&&(c->ttl_ms==0||(c->ttl_ms>=5000&&c->ttl_ms<=30000))&&c->idle_ms>=5000&&c->idle_ms<=120000&&c->dim_percent>=5&&c->dim_percent<=50;
}
void rp_lease(RPState *s,const RPConfig *c,uint64_t now) {
    if(!s->expires_ms||now>=s->expires_ms) s->last_activity_ms=now;
    s->expires_ms=c->ttl_ms?now+c->ttl_ms:0;s->idle_ms=c->idle_ms;s->dim_percent=c->dim_percent;
}
RPAction rp_step(RPState *s,uint64_t now,int network,int current,uint32_t activity,int motion_valid) {
    RPAction a={0,-1};s->current=current;
    if(!network||now>=s->expires_ms) s->expires_ms=0;
    if(activity) { s->last_activity_ms=now;s->activity_flags=activity; }
    if(s->dimmed&&current>=21&&current!=s->applied) { /* Respect a user brightness change. */
        s->dimmed=0;s->original=current;s->last_activity_ms=now;s->activity_flags=16;
    }
    a.keep_awake=s->expires_ms>now;
    if(s->dimmed&&(!a.keep_awake||activity||!motion_valid)) {
        if(current==s->applied&&s->original>=21) a.brightness=s->original;
    } else if(a.keep_awake&&!s->dimmed&&motion_valid&&!activity&&now-s->last_activity_ms>=s->idle_ms&&current>=21&&current<=65536) {
        int dim=(current*(int)s->dim_percent)/100;if(dim<21) dim=21;
        if(dim<current) { s->original=current;a.brightness=dim; }
    }
    return a;
}
void rp_applied(RPState *s,int brightness,int result) {
    s->brightness_result=result;
    if(result>=0) { s->dimmed=brightness!=s->original;s->applied=brightness;s->current=brightness; }
}
static float absolute(float v) { return v<0?-v:v; }
int rp_motion(float acc[3],float gyro[3],float baseline[3],int *initialized,int *consecutive) {
    int moving=0;
    for(unsigned i=0;i<3;i++) {
        if(!(acc[i]==acc[i]&&gyro[i]==gyro[i]&&absolute(acc[i])<100&&absolute(gyro[i])<100)) return -1;
        if(absolute(gyro[i])>.12f||(*initialized&&absolute(acc[i]-baseline[i])>.05f)) moving=1;
    }
    if(!*initialized) { for(unsigned i=0;i<3;i++) baseline[i]=acc[i];*initialized=1;*consecutive=0;return 0; }
    if(moving) (*consecutive)++;else *consecutive=0;
    if(*consecutive>=3) { for(unsigned i=0;i<3;i++) baseline[i]=acc[i];*consecutive=0;return 1; }
    return 0;
}
