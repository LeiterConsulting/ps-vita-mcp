/* Real codec/core with simulated serialized storage/native adapters. */
#include "http.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define BUILD "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#define INSTANCE "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
#define DEVBUILD "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
#define ATTEMPT "dddddddddddddddddddddddddddddddd"
static LBCore core;
static LBReceipt record;
static uint64_t now;
static unsigned claims,launches,saves,cases;
static int present;
static char body[4097],reply[LB_HTTP_REPLY_MIN];
static LBDeferred deferred;

static uint64_t clock_ms(void *ctx) { (void)ctx;return now; }
static int recover(void *ctx,LBReceipt *out) { (void)ctx;(void)out;return 0; }
static int claim(void *ctx,const LBReceipt *in) {
    (void)ctx;claims++;
    if(present) return 1;
    record=*in;present=1;return 0;
}
static int save(void *ctx,const LBReceipt *in) { (void)ctx;record=*in;saves++;return 0; }
static int lookup(void *ctx,const char attempt[33],LBReceipt *out) {
    (void)ctx;
    if(!present||strcmp(attempt,record.attempt)) return 1;
    *out=record;return 0;
}
static LBLaunchResult launch(void *ctx) { (void)ctx;launches++;return (LBLaunchResult){1,0}; }
static void reset(void) {
    claims=launches=saves=0;present=0;now=100;
    memset(&record,0,sizeof(record));memset(&deferred,0,sizeof(deferred));
    LBConfig config={.enabled=1};
    memcpy(config.resident_build,BUILD,65);memcpy(config.instance,INSTANCE,33);
    LBAdapter adapter={clock_ms,recover,claim,save,lookup,launch};
    assert(lb_init(&core,&config,&adapter,0)==LB_OK);
}
static void make(unsigned changed,const char *value) {
    const char *values[]={"\"" ATTEMPT "\"","\"CHRS00003\"","\"" DEVBUILD "\"",
                          "\"" BUILD "\"","\"" INSTANCE "\"","100","1000"};
    if(changed<7) values[changed]=value;
    int count=snprintf(body,sizeof(body),
        "{\"attempt\":%s,\"title_id\":%s,\"expected_devloop_build\":%s,\"resident_build_id\":%s,\"instance_id\":%s,\"issued_ms\":%s,\"ttl_ms\":%s}",
        values[0],values[1],values[2],values[3],values[4],values[5],values[6]);
    assert(count>0&&(size_t)count<sizeof(body));
}
static int call(int admin,const char *method,const char *path,const void *data,size_t size) {
    return lb_http_dispatch(&core,admin,method,path,data,size,reply,sizeof(reply),&deferred);
}
static int post(void) { return call(1,"POST","/devloop-launch",body,strlen(body)); }
static void reject_number(unsigned field,const char *value) {
    reset();make(field,value);assert(post()==400&&!claims&&!launches&&!deferred.armed);cases++;
}
static void rejected_body(const char *value) {
    reset();assert(call(1,"POST","/devloop-launch",value,strlen(value))==400);
    assert(!claims&&!launches&&!deferred.armed);cases++;
}

int main(void) {
    reset();assert(call(1,"GET","/devloop-launch/status",0,0)==200);
    assert(strstr(reply,"\"enabled\":true")&&strstr(reply,"\"blocked\":false")&&strstr(reply,"\"now_ms\":100"));
    assert(strstr(reply,BUILD)&&strstr(reply,INSTANCE)&&!claims&&!launches&&!deferred.armed);cases++;
    reset();assert(lb_set_enabled(&core,0)==LB_OK);
    assert(call(1,"GET","/devloop-launch/status",0,0)==200&&strstr(reply,"\"enabled\":false"));
    make(7,0);assert(post()==403&&!claims&&!deferred.armed);cases++;
    reset();core.blocked=1;
    assert(call(1,"GET","/devloop-launch/status",0,0)==200&&strstr(reply,"\"blocked\":true")&&strstr(reply,"\"enabled\":false"));cases++;
    reset();now=99;assert(call(1,"GET","/devloop-launch/status",0,0)==503&&!claims&&!launches);cases++;
    reset();now=150;assert(call(1,"GET","/devloop-launch/status",0,0)==200);
    now=149;assert(call(1,"GET","/devloop-launch/status",0,0)==503&&core.blocked);
    now=160;make(5,"160");assert(post()==503&&!claims&&!launches);cases++;
    reset();make(7,0);assert(post()==202);
    now=99;assert(call(1,"GET","/devloop-launch/status",0,0)==503&&core.blocked&&saves==1);
    assert(core.current.state==LB_UNKNOWN&&core.current.reason==LB_REASON_CLOCK&&!launches);
    assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==200&&strstr(reply,"\"reason\":\"clock\""));cases++;

    const char *paths[]={"/devloop-launch","/devloop-launch/status","/devloop-launch/" ATTEMPT};
    for(unsigned role=0;role<4;role++) if(role!=1) {
        for(unsigned n=0;n<3;n++) {
            reset();make(7,0);deferred.armed=1;
            assert(call((int)role,n?"GET":"POST",paths[n],n?0:body,n?0:strlen(body))==403);
            assert(!claims&&!launches&&!deferred.armed);cases++;
        }
    }
    reset();assert(call(1,"POST","/devloop-launch/status",0,0)==405&&!claims);cases++;
    reset();assert(call(1,"GET","/devloop-launch",0,0)==405&&!claims);cases++;
    reset();assert(call(1,"GET","/devloop-launch/status","x",1)==400&&!claims);cases++;
    reset();assert(call(1,"GET","/devloop-launch/" ATTEMPT,"x",1)==400&&!claims);cases++;
    const char *unknown[]={"/devloop-launch/observe","/devloop-launch/status?x=1","/devloop-launch/status/",
        "/devloop-launch/" ATTEMPT "/x","/devloop-launch/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","/devloop-launch/.."};
    for(unsigned n=0;n<sizeof(unknown)/sizeof(*unknown);n++) {
        reset();assert(call(1,"GET",unknown[n],0,0)==404&&!claims&&!launches);cases++;
    }
    reset();assert(call(1,"POST","/devloop-launch/observe","{}",2)==404&&!claims&&!launches);cases++;
    reset();assert(call(1,"POST","/devloop-launch/" ATTEMPT,0,0)==405&&!claims);cases++;
    reset();assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==404&&!claims);cases++;

    reset();make(7,0);assert(post()==202&&claims==1&&!launches&&deferred.armed&&!strcmp(deferred.attempt,ATTEMPT));
    assert(strstr(reply,"\"state\":\"queued\"")&&strstr(reply,"\"native_confirmed\":false"));
    assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==200&&!deferred.armed&&!launches);
    assert(strstr(reply,"\"expected_devloop_build\":\"" DEVBUILD "\""));cases++;
    /* Dispatch is exclusively the external service's post-close hook. */
    LBReceipt out={0};
    assert(lb_dispatch_after_response(&core,ATTEMPT,1,&out)==LB_OK&&launches==1);
    assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==200&&strstr(reply,"\"state\":\"submitted\""));
    make(7,0);deferred.armed=1;assert(post()==409&&!deferred.armed&&launches==1&&claims==1);cases++;
    reset();make(7,0);assert(post()==202&&deferred.armed);
    assert(lb_dispatch_after_response(&core,deferred.attempt,0,&out)==LB_OK&&!launches);
    assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==200&&strstr(reply,"\"state\":\"unknown\""));cases++;

    reset();make(7,0);
    assert(lb_http_dispatch(&core,1,"POST","/devloop-launch",body,strlen(body),reply,64,&deferred)==503&&!claims&&!deferred.armed);cases++;
    assert(lb_http_dispatch(&core,1,"POST","/devloop-launch",body,strlen(body),0,0,&deferred)==503&&!claims&&!deferred.armed);cases++;
    assert(lb_http_dispatch(&core,1,"POST","/devloop-launch",body,strlen(body),reply,sizeof(reply),0)==503&&!claims);cases++;
    reset();assert(call(1,"POST","/devloop-launch",body,LB_HTTP_BODY_MAX+1)==413&&!claims);cases++;
    reset();make(7,0);size_t length=strlen(body);body[20]=0;
    assert(call(1,"POST","/devloop-launch",body,length)==400&&!claims);cases++;
    reset();assert(call(1,"POST","/devloop-launch",0,1)==400&&!claims);cases++;

    const char *bad_numbers[]={"-1","+100","0100","1.0","1e2","true","false","null","\"100\"","[]","{}","18446744073709551616"};
    for(unsigned field=5;field<7;field++) for(unsigned n=0;n<sizeof(bad_numbers)/sizeof(*bad_numbers);n++) reject_number(field,bad_numbers[n]);
    reject_number(6,"4294967296");reject_number(6,"0");reject_number(6,"10001");
    reject_number(5,"18446744073709551615");
    rejected_body("");rejected_body("{}");rejected_body("[]");rejected_body("null");
    reset();make(7,0);length=strlen(body);memcpy(body+length," trailing",10);
    assert(post()==400&&!claims);cases++;
    reset();make(7,0);length=strlen(body);snprintf(body+length-1,sizeof(body)-length+1,",\"ttl_ms\":1000}");
    assert(post()==400&&!claims);cases++;
    reset();make(7,0);char *key=strstr(body,"ttl_ms");assert(key);memcpy(key,"badkey",6);
    assert(post()==400&&!claims);cases++;
    reset();make(7,0);key=strstr(body,"ttl_ms");memcpy(key,"issued",6);
    assert(post()==400&&!claims);cases++;
    reset();make(0,"\"ddddddddddddddddddddddddddddddddx\"");assert(post()==400&&!claims);cases++;
    reset();make(0,"\"ddddddddddddddddddddddddddddddd\"");assert(post()==400&&!claims);cases++;
    reset();make(0,"\"DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD\"");assert(post()==400&&!claims);cases++;
    reset();make(0,"\"ddddddddddddddddddddddddddddddd\\u0064\"");assert(post()==400&&!claims);cases++;
    reset();make(1,"\"CHRS00012\"");assert(post()==400&&!claims);cases++;
    reset();make(3,"\"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee\"");assert(post()==412&&!claims);cases++;

    reset();now=UINT64_MAX-1000;
    core.last_ms=now;
    make(5,"18446744073709550615");
    assert(post()==202&&strstr(reply,"\"expires_ms\":18446744073709551615")&&!launches);cases++;
    assert(lb_dispatch_after_response(&core,deferred.attempt,1,&out)==LB_OK&&launches==1);
    LBAuth auth={.role=LB_ROLE_ADMIN};memcpy(auth.resident_build,BUILD,65);memcpy(auth.instance,INSTANCE,33);
    LBObservation observation={.pid=1,.frame=UINT64_MAX-1,.revision=UINT64_MAX,.paused=1};
    memcpy(observation.title,LB_TITLE,10);memcpy(observation.version,"01.04",6);
    memcpy(observation.build,DEVBUILD,65);memcpy(observation.run,INSTANCE,33);
    assert(lb_observe(&core,&auth,ATTEMPT,&observation,&out)==LB_OK);
    observation.frame++;
    assert(lb_observe(&core,&auth,ATTEMPT,&observation,&out)==LB_OK);
    assert(call(1,"GET","/devloop-launch/" ATTEMPT,0,0)==200&&strstr(reply,"observed_script_only"));
    assert(strstr(reply,"\"frame\":18446744073709551615")&&strlen(reply)<sizeof(reply));cases++;
    printf("PASS %u strict broker codec/core cases; no launch occurs inside HTTP dispatch\n",cases);
    return 0;
}
