#include "power_policy.h"
#include "api.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
int main(void) {
    RPConfig c={RP_MAGIC,RC_ABI,30000,5000,20};assert(rp_valid(&c));RPState s={0};rp_lease(&s,&c,1000);
    RPAction a=rp_step(&s,5999,1,50000,0,1);assert(a.keep_awake&&a.brightness==-1);
    a=rp_step(&s,6000,1,50000,0,1);assert(a.brightness==10000);rp_applied(&s,a.brightness,0);
    rp_lease(&s,&c,7000);assert(s.last_activity_ms==1000&&s.dimmed); /* MCP heartbeat is not device interaction. */
    a=rp_step(&s,8000,1,10000,8,1);assert(a.brightness==50000);rp_applied(&s,a.brightness,0);assert(!s.dimmed);
    a=rp_step(&s,13000,1,50000,0,1);assert(a.brightness==10000);rp_applied(&s,a.brightness,-1);assert(!s.dimmed);
    rp_applied(&s,a.brightness,0);a=rp_step(&s,14000,1,25000,0,1);assert(!s.dimmed&&a.brightness==-1&&s.original==25000);
    a=rp_step(&s,19000,1,25000,0,1);assert(a.brightness==5000);rp_applied(&s,a.brightness,0);
    a=rp_step(&s,20000,0,5000,0,1);assert(!a.keep_awake&&a.brightness==25000);rp_applied(&s,a.brightness,0);
    rp_lease(&s,&c,30000);a=rp_step(&s,35000,1,21,0,1);assert(a.brightness==-1);
    a=rp_step(&s,35001,1,50000,0,0);assert(a.brightness==-1); /* Missing motion data inhibits dimming. */
    a=rp_step(&s,35002,1,50000,0,1);assert(a.brightness==10000);rp_applied(&s,a.brightness,0);
    a=rp_step(&s,35003,1,10000,0,0);assert(a.brightness==50000);rp_applied(&s,a.brightness,0);
    a=rp_step(&s,35004,1,50000,0,1);assert(a.brightness==10000);rp_applied(&s,a.brightness,0);
    a=rp_step(&s,60000,1,10000,0,1);assert(!a.keep_awake&&a.brightness==50000);
    c.ttl_ms=30001;assert(!rp_valid(&c));c.ttl_ms=0;assert(rp_valid(&c));c.idle_ms=4999;assert(!rp_valid(&c));c.idle_ms=5000;c.dim_percent=0;assert(!rp_valid(&c));
    float acc[]={0,0,1},gyro[]={0,0,0},baseline[3];int initialized=0,consecutive=0;
    assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==0);
    acc[0]=.02f;assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==0);
    acc[0]=.1f;assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==0);assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==0);assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==1);
    gyro[0]=.2f;for(unsigned i=0;i<2;i++) assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==0);assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==1);
    acc[0]=NAN;assert(rp_motion(acc,gyro,baseline,&initialized,&consecutive)==-1);
    puts("Work lease expiry/offline restore, idle dim, user override, failure, motion/noise and bounds: PASS");
}
