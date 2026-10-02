#include "core.h"
#include "sha256.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
extern unsigned test_draw_calls;
static DevCore core;
static Input input;
static char error[256];
static const char *good="local ticks=0; return {update=function(dt,i) ticks=ticks+1; vita.metric('ticks',ticks); vita.metric('buttons',i.buttons); vita.metric('touches',#i.front); vita.metric('ax',i.motion.ax) end,draw=function() vita.rect(24,100,900,380,vita.rgb(20,32,49)); vita.text(40,140,1,vita.rgb(64,220,191),'HOST FIXTURE') end}";
static DevCommand upload(const char *name,const char *source) {
    DevCommand cmd={0}; cmd.script_upload=true; cmd.expected_revision=core.revision;
    snprintf(cmd.script_name,sizeof(cmd.script_name),"%s",name); snprintf(cmd.script_source,sizeof(cmd.script_source),"%s",source);
    dev_sha256(source,strlen(source),cmd.script_sha256); return cmd;
}
static bool load(const char *name,const char *source) { DevCommand cmd=upload(name,source); return dev_apply(&core,&cmd,error,sizeof(error))==200; }
static void control(const char *name) {
    DevCommand cmd={0}; cmd.expected_revision=core.revision; snprintf(cmd.action,sizeof(cmd.action),"%s",name);
    assert(dev_apply(&core,&cmd,error,sizeof(error))==200);
}
static void reject(const char *source,const char *message) {
    unsigned revision=core.revision; char hash[65]; memcpy(hash,core.script.sha256,65);
    DevCommand cmd=upload("bad",source); assert(dev_apply(&core,&cmd,error,sizeof(error))==422);
    assert(strstr(error,message)); assert(core.revision==revision&&!strcmp(core.script.sha256,hash)&&!core.script.faulted);
}
static void sample(void) { dev_tick(&core,&input,core.sampled_ms+17); }
int main(void) {
    char hash[65]; dev_sha256("",0,hash); assert(!strcmp(hash,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));
    dev_sha256("abc",3,hash); assert(!strcmp(hash,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));
    const char *long_vector="abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
    dev_sha256(long_vector,strlen(long_vector),hash); assert(!strcmp(hash,"248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
    puts("PASS device SHA-256 empty, short and multi-block official vectors");
    dev_init(&core); input.lx=input.ly=input.rx=input.ry=128; input.dt=1.0f/60; input.motion_result=0; input.buttons=BTN_CIRCLE;
    input.front.count=2; input.acceleration.x=.25f; core.input=input;
    assert(load("first",good)&&core.paused&&core.script.active&&core.script.memory_bytes<SCRIPT_MEMORY_MAX);
    assert(core.script.metric_count==4&&core.script.metrics[1].value==BTN_CIRCLE&&core.script.metrics[2].value==2&&core.script.metrics[3].value==.25f);
    script_render(); assert(test_draw_calls==2);
    unsigned updates=core.script.updates; sample(); assert(core.script.updates==updates);
    control("resume"); sample(); assert(core.script.updates==updates+1); control("pause");
    puts("PASS transactional load, real-shaped input samples, metrics, buffered rendering and pause/resume");
    reject("return {update=function() end, draw=function(}","bad.lua");
    reject("return {}","must return a table");
    reject("error('quoted \"oops\"')","oops");
    reject("return {init=function() error('init fail') end,update=function() end,draw=function() end}","init fail");
    reject("return {update=function() error('update fail') end,draw=function() end}","update fail");
    reject("return {update=function() end,draw=function() error('draw fail') end}","draw fail");
    puts("PASS syntax, interface, chunk/init/update/draw errors reject edits without changing active VM or revision");
    reject("while true do end","instruction budget");
    reject("return {update=function() while true do end end,draw=function() end}","instruction budget");
    reject("local s=string.rep('x',2000000); return {}","memory");
    reject("return {update=function() end,draw=function() for i=1,257 do vita.circle(1,1,1) end end}","drawing budget");
    reject("return {update=function() end,draw=function() vita.circle(0/0,1,1) end}","finite");
    puts("PASS infinite-loop, memory, drawing and non-finite argument limits recover safely");
    reject("assert(io and io.open)","assertion"); reject("assert(os)","assertion"); reject("assert(package)","assertion");
    reject("assert(debug)","assertion"); reject("assert(pcall)","assertion"); reject("assert(setmetatable)","assertion");
    reject("assert(load)","assertion"); reject("assert(coroutine)","assertion"); reject("assert(string.dump)","assertion");
    puts("PASS no script filesystem, process, native-module, debug, coroutine or error-catching escape APIs");
    DevCommand wrong=upload("wrong",good); wrong.expected_revision--; unsigned revision=core.revision;
    assert(dev_apply(&core,&wrong,error,sizeof(error))==409&&core.revision==revision);
    wrong.expected_revision=core.revision; wrong.script_sha256[0]=wrong.script_sha256[0]=='a'?'b':'a';
    assert(dev_apply(&core,&wrong,error,sizeof(error))==422&&core.revision==revision);
    puts("PASS revision conflicts and source hash mismatches preserve working experiment");
    assert(load("second","local n=0; return {update=function() n=n+1; if n>1 then error('late fault') end end,draw=function() vita.circle(500,300,12) end}"));
    assert(core.script.rollback_available); control("resume"); sample(); assert(core.paused&&core.script.faulted&&strstr(core.script.error,"late fault"));
    input.pressed=BTN_START; sample(); assert(core.paused); input.pressed=0;
    DevCommand resume={0}; resume.expected_revision=core.revision; snprintf(resume.action,sizeof(resume.action),"resume");
    assert(dev_apply(&core,&resume,error,sizeof(error))==409);
    control("script_rollback"); assert(!strcmp(core.script.name,"first")&&!core.script.faulted&&core.paused&&!core.script.rollback_available);
    control("script_restart"); assert(core.script.updates==0&&core.script.metrics[0].value==1);
    puts("PASS later runtime faults pause; console/MCP resume cannot bypass fault; rollback and restart recover");
    float native_x=core.world.x; control("native"); assert(!core.script.active&&core.world.x==native_x&&core.paused);
    control("script_activate"); assert(core.script.active&&core.paused);
    control("resume"); input.resumed=true; input.dt=0; sample(); assert(core.paused); input.resumed=false; input.dt=1.0f/60;
    puts("PASS native fallback preserves physics; reactivation and sleep/resume stay paused");
    FILE *source=fopen("experiments/bounce.lua","rb"); assert(source); char buffer[SCRIPT_MAX+1]; size_t length=fread(buffer,1,SCRIPT_MAX,source); fclose(source); buffer[length]=0;
    assert(load("bounce",buffer)); control("resume");
    for(unsigned n=0;n<6000;n++) sample();
    assert(!core.script.faulted&&core.script.updates==6000&&core.script.peak_memory_bytes<=SCRIPT_MEMORY_MAX);
    source=fopen("experiments/input_scope.lua","rb"); assert(source); length=fread(buffer,1,SCRIPT_MAX,source); fclose(source); buffer[length]=0;
    assert(load("input_scope",buffer)); control("resume"); for(unsigned n=0;n<100;n++) sample(); assert(!core.script.faulted);
    puts("PASS both shipped experiments and 6000-frame soak with bounded Lua allocation");
    char json[DEV_JSON_MAX]; dev_script_json(&core,json,sizeof(json));
    FILE *fixture=fopen("build/host/script-fixture.json","w"); assert(fixture); fprintf(fixture,"%s\n",json); fclose(fixture);
    dev_error_json(json,sizeof(json),"quoted \"message\" and \\ newline\n");
    assert(strstr(json,"\\\"message\\\"")&&strstr(json,"\\\\")&&strstr(json,"\\u000a"));
    puts("PASS complete script metrics/status and escaped error JSON");
    script_shutdown(); puts("10 Lua runtime test groups passed; all rendering/input evidence is host simulated."); return 0;
}
