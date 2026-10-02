#include "core.h"
#include "math_helpers.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>
#include <errno.h>

void dev_log(DevCore *c,const char *message) {
    snprintf(c->logs[c->log_sequence%12],128,"%.127s",message); c->log_sequence++;
}
void dev_init(DevCore *c) {
    script_shutdown();
    memset(c,0,sizeof(*c)); world_init(&c->world); c->params=physics_defaults(); c->paused=true; c->revision=1;
    dev_log(c,"DevLoop ready; experiment starts paused");
}
static void reset(DevCore *c) { world_init(&c->world); c->accumulator=0; }
void dev_tick(DevCore *c,const Input *in,uint64_t ms) {
    c->input=*in; c->sampled_ms=ms; c->frame++;
    if(in->resumed) { c->paused=true; c->accumulator=0; c->old_count=0; c->revision++; dev_log(c,"Resume detected; experiment paused"); }
    if(!in->resumed&&(in->pressed&BTN_START)&&!(c->script.active&&c->script.faulted)) { c->paused=!c->paused; c->accumulator=0; c->revision++; dev_log(c,c->paused?"Paused on console":"Resumed on console"); }
    if(c->script.active) {
        if(!script_frame(in,c->paused)) { c->paused=true; c->revision++; dev_log(c,"Lua fault; paused, rollback or reload available"); }
        script_info(&c->script); char logs[8][128]; unsigned count=script_take_logs(logs);
        for(unsigned n=0;n<count;n++) dev_log(c,logs[n]);
        return;
    }
    if(in->pressed&BTN_CROSS) { reset(c); c->revision++; dev_log(c,"Reset on console"); }
    if(in->pressed&BTN_TRIANGLE) { world_clear_added(&c->world); c->revision++; dev_log(c,"Added obstacles cleared"); }
    if(in->pressed&BTN_SQUARE) { c->stick_only=!c->stick_only; c->revision++; }
    if(in->pressed&BTN_L) { c->invert_x=!c->invert_x; c->revision++; }
    if(in->pressed&BTN_R) { c->invert_y=!c->invert_y; c->revision++; }
    if(in->motion_result>=0) {
        if(!c->neutral_valid||(in->pressed&BTN_SELECT)) {
            c->neutral=c->filtered=in->acceleration; c->neutral_valid=true;
            if(in->pressed&BTN_SELECT) c->revision++;
            dev_log(c,"Motion neutral captured");
        }
        float alpha=1-expf(-12*in->dt);
        c->filtered.x+=(in->acceleration.x-c->filtered.x)*alpha;
        c->filtered.y+=(in->acceleration.y-c->filtered.y)*alpha;
        c->filtered.z+=(in->acceleration.z-c->filtered.z)*alpha;
    }
    for(int n=0;n<in->front.count;n++) {
        Contact p=in->front.points[n]; bool fresh=true;
        for(int j=0;j<c->old_count;j++) if(c->old_ids[j]==p.id) fresh=false;
        float x=p.x*SCREEN_W,y=p.y*SCREEN_H;
        if(fresh&&x>=c->world.left&&x<=c->world.right&&y>=c->world.top&&y<=c->world.bottom&&world_add_obstacle(&c->world,x,y)) {
            c->revision++; dev_log(c,"Touch obstacle added");
        }
    }
    c->old_count=in->front.count; for(int n=0;n<c->old_count;n++) c->old_ids[n]=in->front.points[n].id;
    c->force_x=axis_deadzone(in->lx,0.12f); c->force_y=axis_deadzone(in->ly,0.12f);
    if(!c->stick_only&&c->neutral_valid&&in->motion_result>=0) {
        float x,y; tilt_force(c->filtered.x,c->filtered.y,c->filtered.z,c->neutral.x,c->neutral.y,c->neutral.z,&x,&y);
        c->force_x=clampf(c->force_x+(c->invert_x?-x:x),-1,1);
        c->force_y=clampf(c->force_y+(c->invert_y?-y:y),-1,1);
    }
    if(!c->paused) {
        c->accumulator+=in->dt;
        while(c->accumulator>=1.0f/120) {
            world_step_configured(&c->world,1.0f/120,c->force_x,c->force_y,in->back.count>0||(in->buttons&BTN_CIRCLE),&c->params);
            c->accumulator-=1.0f/120;
        }
    }
}
static int bad(char *out,size_t capacity,const char *message) { snprintf(out,capacity,"%s",message); return 400; }
int dev_parse_command(const char *path,const char *body,DevCommand *cmd,char *error,size_t cap) {
    memset(cmd,0,sizeof(*cmd)); cmd->parameters=strcmp(path,"/parameters")==0;
    if(!cmd->parameters&&strcmp(path,"/control")!=0) return bad(error,cap,"Unknown command path");
    if(strlen(body)>=512) return bad(error,cap,"Command body too long");
    char text[512]; strcpy(text,body); char *cursor=text; unsigned seen=0;
    while(cursor&&*cursor) {
        char *next=strchr(cursor,'&'); if(next) *next++=0;
        char *value=strchr(cursor,'='); if(!value||value==cursor) return bad(error,cap,"Expected form key=value");
        *value++=0; unsigned field=0;
        if(!strcmp(cursor,"expected_revision")) {
            field=1;
            if(!*value) return bad(error,cap,"Missing expected revision");
            for(char *p=value;*p;p++) if(*p<'0'||*p>'9') return bad(error,cap,"Invalid revision");
            errno=0; unsigned long v=strtoul(value,NULL,10);
            if(errno||v>UINT32_MAX) return bad(error,cap,"Invalid revision");
            cmd->expected_revision=(uint32_t)v;
        } else if(!cmd->parameters&&!strcmp(cursor,"action")) {
            field=2;
            const char *actions[]={"pause","resume","reset","recenter","stick","tilt","clear_obstacles","script_restart","script_rollback","native","script_activate"}; bool known=false;
            for(unsigned n=0;n<sizeof(actions)/sizeof(actions[0]);n++) if(!strcmp(value,actions[n])) known=true;
            if(!known) return bad(error,cap,"Unknown action");
            snprintf(cmd->action,sizeof(cmd->action),"%s",value);
        } else if(cmd->parameters) {
            float *target=NULL,lo=0,hi=0;
            if(!strcmp(cursor,"gravity")) { field=2; target=&cmd->params.gravity; lo=50; hi=1500; }
            if(!strcmp(cursor,"drag")) { field=4; target=&cmd->params.drag; lo=0; hi=8; }
            if(!strcmp(cursor,"brake")) { field=8; target=&cmd->params.brake; lo=1; hi=30; }
            if(!strcmp(cursor,"max_speed")) { field=16; target=&cmd->params.max_speed; lo=50; hi=500; }
            if(!target) return bad(error,cap,"Unknown parameter");
            char *end; errno=0; float v=strtof(value,&end);
            if(errno||end==value||*end||!isfinite(v)||v<lo||v>hi) return bad(error,cap,"Parameter outside allowed range");
            *target=v; cmd->mask|=field;
        } else return bad(error,cap,"Unknown field");
        if(seen&field) return bad(error,cap,"Duplicate field");
        seen|=field; cursor=next;
        if(cursor&&!*cursor) return bad(error,cap,"Trailing separator");
    }
    if(!(seen&1)||(!cmd->parameters&&!(seen&2))||(cmd->parameters&&!cmd->mask)) return bad(error,cap,"Required fields missing");
    return 200;
}
int dev_apply(DevCore *c,const DevCommand *cmd,char *error,size_t cap) {
    if(cmd->expected_revision!=c->revision) { snprintf(error,cap,"Revision changed; read status before retrying"); return 409; }
    if(cmd->script_upload) {
        bool ok=script_load(cmd->script_name,cmd->script_source,cmd->script_sha256,&c->input,error,cap);
        script_info(&c->script);
        if(!ok) { dev_log(c,"Lua edit rejected; current experiment preserved"); return 422; }
        c->paused=true; c->accumulator=0; dev_log(c,"Lua experiment loaded and preflight checked; paused");
    } else if(!strncmp(cmd->action,"script_",7)||!strcmp(cmd->action,"native")) {
        bool ok=script_control(cmd->action,&c->input,error,cap); script_info(&c->script);
        if(!ok) return 409;
        c->paused=true; c->accumulator=0; c->old_count=0; dev_log(c,"Experiment mode/recovery changed; paused");
    } else if(cmd->parameters) {
        if(c->script.active) { snprintf(error,cap,"Physics parameters belong to native mode; switch to native first"); return 409; }
        if(cmd->mask&2) c->params.gravity=cmd->params.gravity;
        if(cmd->mask&4) c->params.drag=cmd->params.drag;
        if(cmd->mask&8) c->params.brake=cmd->params.brake;
        if(cmd->mask&16) c->params.max_speed=cmd->params.max_speed;
        dev_log(c,"Physics parameters changed through bridge");
    } else {
        if(c->script.active&&strcmp(cmd->action,"pause")&&strcmp(cmd->action,"resume")) {
            snprintf(error,cap,"Native physics action requires native mode; use Lua restart or native"); return 409;
        }
        if(c->script.active&&c->script.faulted&&!strcmp(cmd->action,"resume")) {
            snprintf(error,cap,"Lua is faulted; restart, reload or roll back before resume"); return 409;
        }
        if(!strcmp(cmd->action,"pause")) { c->paused=true; c->accumulator=0; }
        if(!strcmp(cmd->action,"resume")) { c->paused=false; c->accumulator=0; }
        if(!strcmp(cmd->action,"reset")) reset(c);
        if(!strcmp(cmd->action,"stick")) c->stick_only=true;
        if(!strcmp(cmd->action,"tilt")) c->stick_only=false;
        if(!strcmp(cmd->action,"clear_obstacles")) world_clear_added(&c->world);
        if(!strcmp(cmd->action,"recenter")) {
            if(c->input.motion_result<0) { snprintf(error,cap,"Motion sample unavailable"); return 409; }
            c->neutral=c->filtered=c->input.acceleration; c->neutral_valid=true;
        }
        char message[100]; snprintf(message,sizeof(message),"Bridge action: %s",cmd->action); dev_log(c,message);
    }
    c->revision++; return 200;
}
static float json_number(float value) { return isfinite(value)?value:0; }
void dev_status_json(const DevCore *c,char *out,size_t cap) {
    snprintf(out,cap,"{\"protocol\":1,\"app\":\"Vita DevLoop\",\"version\":\"%s\",\"experiment\":\"%s\",\"revision\":%u,\"frame\":%llu,\"sampled_ms\":%llu,\"fps\":%.2f,\"frame_ms\":%.3f,\"paused\":%s,\"mode\":\"%s\",\"parameters\":{\"gravity\":%.3f,\"drag\":%.3f,\"brake\":%.3f,\"max_speed\":%.3f},\"ball\":{\"x\":%.3f,\"y\":%.3f,\"vx\":%.3f,\"vy\":%.3f},\"score\":%d,\"added_obstacles\":%d}",
        DEV_VERSION,c->script.active?"lua":"tilt_playground",c->revision,(unsigned long long)c->frame,(unsigned long long)c->sampled_ms,json_number(c->input.fps),json_number(c->input.dt*1000),c->paused?"true":"false",c->stick_only?"stick":"tilt+stick",c->params.gravity,c->params.drag,c->params.brake,c->params.max_speed,json_number(c->world.x),json_number(c->world.y),json_number(c->world.vx),json_number(c->world.vy),c->world.score,c->world.obstacle_count-3);
}
static void append(char *out,size_t cap,size_t *used,const char *format,...) {
    if(*used>=cap) return;
    va_list args; va_start(args,format); int n=vsnprintf(out+*used,cap-*used,format,args); va_end(args);
    if(n>0) *used+=(size_t)n;
}
static void json_string(char *out,size_t cap,size_t *used,const char *value) {
    append(out,cap,used,"\"");
    for(const unsigned char *p=(const unsigned char*)value;*p;p++) {
        if(*p=='\"'||*p=='\\') append(out,cap,used,"\\%c",*p);
        else if(*p<32) append(out,cap,used,"\\u%04x",*p);
        else append(out,cap,used,"%c",*p);
    }
    append(out,cap,used,"\"");
}
void dev_error_json(char *out,size_t cap,const char *message) {
    size_t used=0; append(out,cap,&used,"{\"error\":"); json_string(out,cap,&used,message); append(out,cap,&used,"}");
}
void dev_script_json(const DevCore *c,char *out,size_t cap) {
    const DevScriptInfo *s=&c->script; size_t used=0;
    append(out,cap,&used,"{\"revision\":%u,\"frame\":%llu,\"sampled_ms\":%llu,\"runtime\":\"Lua 5.4.9\",\"loaded\":%s,\"active\":%s,\"faulted\":%s,\"paused\":%s,\"name\":",
        c->revision,(unsigned long long)c->frame,(unsigned long long)c->sampled_ms,s->loaded?"true":"false",s->active?"true":"false",s->faulted?"true":"false",c->paused?"true":"false");
    json_string(out,cap,&used,s->name); append(out,cap,&used,",\"sha256\":"); json_string(out,cap,&used,s->sha256);
    append(out,cap,&used,",\"source_bytes\":%u,\"updates\":%u,\"draw_commands\":%u,\"memory_bytes\":%u,\"peak_memory_bytes\":%u,\"update_ms\":%.3f,\"draw_ms\":%.3f,\"rollback_available\":%s,\"previous_name\":",
        s->source_bytes,s->updates,s->draw_commands,s->memory_bytes,s->peak_memory_bytes,json_number(s->update_ms),json_number(s->draw_ms),s->rollback_available?"true":"false");
    json_string(out,cap,&used,s->previous_name); append(out,cap,&used,",\"previous_sha256\":"); json_string(out,cap,&used,s->previous_sha256);
    append(out,cap,&used,",\"error\":"); json_string(out,cap,&used,s->error);
    append(out,cap,&used,",\"metrics\":{");
    for(unsigned n=0;n<s->metric_count;n++) { append(out,cap,&used,"%s",n?",":""); json_string(out,cap,&used,s->metrics[n].name); append(out,cap,&used,":%.5f",json_number(s->metrics[n].value)); }
    append(out,cap,&used,"},\"limits\":{\"source_bytes\":%u,\"memory_bytes_per_vm\":%u,\"instructions_per_callback\":20000,\"draw_commands\":%u}}",SCRIPT_MAX,SCRIPT_MEMORY_MAX,SCRIPT_DRAW_MAX);
}
static void panel_json(const TouchPanel *p,char *out,size_t cap,size_t *used) {
    append(out,cap,used,"{\"read_result\":%d,\"panel_result\":%d,\"sampling_result\":%d,\"contacts\":[",p->read_result,p->panel_result,p->start_result);
    for(int n=0;n<p->count;n++) { Contact v=p->points[n]; append(out,cap,used,"%s{\"id\":%u,\"x\":%.5f,\"y\":%.5f,\"raw_x\":%d,\"raw_y\":%d}",n?",":"",v.id,json_number(v.x),json_number(v.y),v.raw_x,v.raw_y); }
    append(out,cap,used,"]}");
}
void dev_input_json(const DevCore *c,char *out,size_t cap) {
    const Input *i=&c->input; size_t used=0;
    append(out,cap,&used,"{\"revision\":%u,\"frame\":%llu,\"sampled_ms\":%llu,\"buttons\":%u,\"controller_read\":%d,\"sticks\":{\"lx\":%u,\"ly\":%u,\"rx\":%u,\"ry\":%u},\"motion\":{\"read_result\":%d,\"acceleration\":[%.5f,%.5f,%.5f],\"gyro\":[%.5f,%.5f,%.5f]},\"front\":",
        c->revision,(unsigned long long)c->frame,(unsigned long long)c->sampled_ms,i->buttons,i->ctrl_result,i->lx,i->ly,i->rx,i->ry,i->motion_result,json_number(i->acceleration.x),json_number(i->acceleration.y),json_number(i->acceleration.z),json_number(i->gyro.x),json_number(i->gyro.y),json_number(i->gyro.z));
    panel_json(&i->front,out,cap,&used); append(out,cap,&used,",\"rear\":"); panel_json(&i->back,out,cap,&used); append(out,cap,&used,"}");
}
void dev_logs_json(const DevCore *c,char *out,size_t cap) {
    size_t used=0; unsigned first=c->log_sequence>12?c->log_sequence-12:0;
    append(out,cap,&used,"{\"revision\":%u,\"frame\":%llu,\"sampled_ms\":%llu,\"sequence\":%u,\"entries\":[",c->revision,(unsigned long long)c->frame,(unsigned long long)c->sampled_ms,c->log_sequence);
    for(unsigned n=first;n<c->log_sequence;n++) {
        append(out,cap,&used,"%s{\"sequence\":%u,\"message\":\"",n>first?",":"",n+1);
        for(const char *p=c->logs[n%12];*p;p++) {
            if(*p=='"'||*p=='\\') append(out,cap,&used,"\\%c",*p);
            else if((unsigned char)*p>=32) append(out,cap,&used,"%c",*p);
        }
        append(out,cap,&used,"\"}");
    }
    append(out,cap,&used,"]}");
}
