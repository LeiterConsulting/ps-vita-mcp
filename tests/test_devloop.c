#include "core.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static DevCommand parse(const char *path,const char *body) {
    DevCommand cmd; char error[128]; assert(dev_parse_command(path,body,&cmd,error,sizeof(error))==200); return cmd;
}
static void apply(DevCore *c,const char *path,const char *body) {
    DevCommand cmd=parse(path,body); char error[128]; assert(dev_apply(c,&cmd,error,sizeof(error))==200);
}
int main(void) {
    DevCore c; dev_init(&c); Input in={0}; in.lx=in.ly=in.rx=in.ry=128; in.dt=1.0f/60; in.motion_result=-1;
    assert(c.paused&&c.revision==1); float x=c.world.x;
    in.lx=255; for(int n=0;n<10;n++) dev_tick(&c,&in,n*17); assert(c.world.x==x);
    apply(&c,"/control","expected_revision=1&action=resume"); dev_tick(&c,&in,200); assert(c.world.x>x);
    apply(&c,"/control","expected_revision=2&action=pause"); x=c.world.x; dev_tick(&c,&in,217); assert(c.world.x==x);
    puts("PASS paused/resume commands alter actual experiment behavior");
    char error[128]; DevCommand cmd=parse("/parameters","expected_revision=2&gravity=1000");
    assert(dev_apply(&c,&cmd,error,sizeof(error))==409&&c.params.gravity==620&&c.revision==3);
    const char *bad[]={"expected_revision=3&gravity=700&drag=nan","expected_revision=3&gravity=1501","expected_revision=3&gravity=50&gravity=60","expected_revision=3&unknown=1","expected_revision=-1&gravity=700","expected_revision=4294967296&gravity=700","gravity=700","expected_revision=3&","expected_revision=3&drag=1oops"};
    for(unsigned n=0;n<sizeof(bad)/sizeof(bad[0]);n++) assert(dev_parse_command("/parameters",bad[n],&cmd,error,sizeof(error))==400);
    assert(c.params.gravity==620&&c.revision==3);
    apply(&c,"/parameters","expected_revision=3&gravity=1000&drag=2&brake=15&max_speed=200");
    assert(c.params.gravity==1000&&c.params.drag==2&&c.params.brake==15&&c.params.max_speed==200&&c.revision==4);
    puts("PASS atomic parameter parsing, ranges, duplicate rejection and revision conflicts");
    World slow,fast; world_init(&slow); world_init(&fast); PhysicsParams p=physics_defaults(),q=p; q.gravity=1000;
    world_step_configured(&slow,1.0f/60,1,0,false,&p); world_step_configured(&fast,1.0f/60,1,0,false,&q); assert(fast.vx>slow.vx);
    puts("PASS configurable gravity changes integrated acceleration");
    apply(&c,"/control","expected_revision=4&action=resume"); in.resumed=true; in.pressed=BTN_START; in.dt=0; x=c.world.x; dev_tick(&c,&in,5000);
    assert(c.paused&&c.revision==6&&c.world.x==x);
    cmd=parse("/control","expected_revision=6&action=recenter"); assert(dev_apply(&c,&cmd,error,sizeof(error))==409&&c.revision==6);
    in.resumed=false; in.pressed=0; in.motion_result=0; in.acceleration.z=1; dev_tick(&c,&in,5017);
    apply(&c,"/control","expected_revision=6&action=recenter"); assert(c.neutral_valid&&c.neutral.z==1);
    apply(&c,"/control","expected_revision=7&action=reset"); assert(c.world.x==106&&c.world.score==0&&c.world.obstacle_count==3);
    puts("PASS sleep safety, unavailable recenter rejection and reset");
    FILE *out=fopen("build/host/devloop-fixtures.jsonl","w"); assert(out);
    char json[DEV_JSON_MAX]; in.acceleration.x=NAN; in.gyro.y=INFINITY; in.front.count=MAX_TOUCHES; in.back.count=MAX_TOUCHES;
    for(int n=0;n<MAX_TOUCHES;n++) { in.front.points[n].id=(unsigned)n; in.front.points[n].x=.2f; in.front.points[n].y=.3f; in.back.points[n]=in.front.points[n]; }
    dev_tick(&c,&in,5034); dev_status_json(&c,json,sizeof(json)); fprintf(out,"%s\n",json);
    dev_input_json(&c,json,sizeof(json)); fprintf(out,"%s\n",json); assert(!strstr(json,"nan")&&!strstr(json,"inf"));
    for(int n=0;n<20;n++) dev_log(&c,"Escaped \"quote\" and \\ slash");
    dev_logs_json(&c,json,sizeof(json)); fprintf(out,"%s\n",json); fclose(out);
    puts("PASS bounded complete sample serialization and twelve-entry escaped log ring");
    return 0;
}
