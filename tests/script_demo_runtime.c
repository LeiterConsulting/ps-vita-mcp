/* Exact generated demo sources through the shared real Lua/core runtime.
 * Input, clocks and rendering are host fixtures; this is not Vita acceptance. */
#include "core.h"
#include "sha256.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern unsigned test_draw_calls;
static DevCore core;
static Input input;
static char error[256];

static float metric(const char *name) {
    for(unsigned n=0;n<core.script.metric_count;n++) {
        if(!strcmp(core.script.metrics[n].name,name)) {
            assert(isfinite(core.script.metrics[n].value));
            return core.script.metrics[n].value;
        }
    }
    assert(!"Expected metric absent");
    return 0;
}

static void load(const char *name,const char *source) {
    DevCommand command={0};
    command.script_upload=true;
    command.expected_revision=core.revision;
    snprintf(command.script_name,sizeof(command.script_name),"%s",name);
    assert(strlen(source)<=SCRIPT_MAX);
    memcpy(command.script_source,source,strlen(source)+1);
    dev_sha256(source,strlen(source),command.script_sha256);
    assert(dev_apply(&core,&command,error,sizeof(error))==200);
    assert(core.paused&&core.script.active&&!core.script.faulted);
    assert(!strcmp(core.script.sha256,command.script_sha256));
}

static void action(const char *name) {
    DevCommand command={0};
    command.expected_revision=core.revision;
    snprintf(command.action,sizeof(command.action),"%s",name);
    assert(dev_apply(&core,&command,error,sizeof(error))==200);
}

static void sample(void) {
    dev_tick(&core,&input,core.sampled_ms+17);
    assert(!core.script.faulted);
}

static void read_source(const char *path,char out[SCRIPT_MAX+1]) {
    FILE *file=fopen(path,"rb");
    assert(file);
    size_t length=fread(out,1,SCRIPT_MAX+1,file);
    assert(!ferror(file)&&length>0&&length<=SCRIPT_MAX);
    assert(fclose(file)==0);
    out[length]=0;
    assert(strlen(out)==length);
}

int main(int argc,char **argv) {
    assert(argc==4);
    char sources[2][SCRIPT_MAX+1],hashes[2][65];
    read_source(argv[1],sources[0]);
    read_source(argv[2],sources[1]);
    dev_init(&core);
    input.lx=input.ly=input.rx=input.ry=128;
    input.dt=1.0f/60;
    input.fps=60;
    input.ctrl_result=input.motion_result=0;
    core.input=input;
    const char *original="local n=0; return {update=function() n=n+1; vita.metric('original_ticks',n) end,draw=function() vita.rect(24,100,10,10,vita.rgb(1,2,3)) end}";
    load("original",original);
    action("resume");
    for(unsigned n=0;n<3;n++) sample();
    action("pause");
    unsigned original_updates=core.script.updates;
    float original_ticks=metric("original_ticks");
    char original_hash[65];
    memcpy(original_hash,core.script.sha256,65);
    World original_world=core.world;
    PhysicsParams original_params=core.params;
    const char *names[2]={"steady","swift"};
    const float speeds[2]={60,120};
    /* Deliberately unequal elapsed times reproduce latency-biased cumulative
     * distance: steady travels farther, while swift must win normalized rate. */
    const unsigned frames[2]={300,120};
    float distances[2],ticks[2],elapsed[2],rates[2];
    for(unsigned index=0;index<2;index++) {
        dev_sha256(sources[index],strlen(sources[index]),hashes[index]);
        load(names[index],sources[index]);
        assert(core.script.metric_count==5&&core.script.updates==0);
        assert(metric("distance")==0&&metric("ticks")==1&&metric("speed")==speeds[index]);
        assert(metric("elapsed")==0&&metric("rate")==0);
        assert(core.script.draw_commands==4&&core.script.rollback_available);
        test_draw_calls=0;
        script_render();
        assert(test_draw_calls==4);
        sample(); /* Paused draw executes; update count and distance remain frozen. */
        assert(core.script.updates==0&&metric("distance")==0&&metric("ticks")==1);
        action("resume");
        for(unsigned n=0;n<frames[index];n++) {
            sample();
            test_draw_calls=0;
            script_render();
            assert(test_draw_calls==4&&core.script.memory_bytes<=SCRIPT_MEMORY_MAX);
        }
        action("pause");
        distances[index]=metric("distance");
        ticks[index]=metric("ticks");
        elapsed[index]=metric("elapsed");
        rates[index]=metric("rate");
        assert(core.script.updates==frames[index]&&ticks[index]==frames[index]+1);
        assert(fabsf(elapsed[index]-frames[index]/60.0f)<.01f);
        assert(fabsf(distances[index]-frames[index]/60.0f*speeds[index])<.01f);
        assert(fabsf(rates[index]-speeds[index])<.01f&&metric("speed")==speeds[index]);
        assert(core.script.peak_memory_bytes<=SCRIPT_MEMORY_MAX);
        assert(!strcmp(core.script.sha256,hashes[index]));
        action("script_rollback");
        assert(core.paused&&core.script.active&&!core.script.faulted);
        assert(!strcmp(core.script.name,"original")&&!strcmp(core.script.sha256,original_hash));
        assert(core.script.updates==original_updates&&metric("original_ticks")==original_ticks);
        assert(!memcmp(&core.world,&original_world,sizeof(original_world)));
        assert(!memcmp(&core.params,&original_params,sizeof(original_params)));
        puts("PASS exact generated source preflight, bounded updates, four draw calls and retained original VM restoration");
    }
    assert(distances[0]>distances[1]&&rates[1]>rates[0]);
    FILE *report=fopen(argv[3],"w");
    assert(report);
    assert(fprintf(report,"{\"scope\":\"real shared Lua/core with host input and rendering\",\"steady\":{\"distance\":%.5f,\"ticks\":%.0f,\"speed\":60,\"elapsed\":%.5f,\"rate\":%.5f,\"updates\":%u,\"sha256\":\"%s\"},\"swift\":{\"distance\":%.5f,\"ticks\":%.0f,\"speed\":120,\"elapsed\":%.5f,\"rate\":%.5f,\"updates\":%u,\"sha256\":\"%s\"},\"selection_metric\":\"rate\",\"best\":\"swift\",\"original_vm_restored_paused\":true,\"native_world_unchanged\":true}\n",
                   distances[0],ticks[0],elapsed[0],rates[0],frames[0],hashes[0],
                   distances[1],ticks[1],elapsed[1],rates[1],frames[1],hashes[1])>0);
    assert(fclose(report)==0);
    script_shutdown();
    puts("PASS swift rate exceeds steady despite smaller cumulative distance; real Lua ranking and original paused VM restoration verified");
    return 0;
}
