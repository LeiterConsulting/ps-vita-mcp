#include "script_runtime.h"
#include "sha256.h"
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <time.h>

typedef struct { unsigned type; float values[4]; uint32_t color; char text[97]; } Draw;
typedef struct {
    lua_State *lua; size_t memory,peak; unsigned instructions,draw_count,log_count,updates;
    int callbacks,phase; bool faulted;
    char name[33],sha256[65],source[SCRIPT_MAX+1],error[256],logs[8][128];
    Draw drawing[SCRIPT_DRAW_MAX]; Input input;
    float update_ms,draw_ms;
    unsigned metric_count; DevMetric metrics[8];
} Script;
static Script *current,*previous;
static bool active;
static char last_error[256];

static Script *context(lua_State *L) { return *(Script**)lua_getextraspace(L); }
static void clean_message(char *out,size_t capacity,const char *text) {
    snprintf(out,capacity,"%s",text?text:"Lua error without a string message");
    for(char *p=out;*p;p++) if((unsigned char)*p<32||(unsigned char)*p>126) *p=' ';
}
static void *allocate(void *user,void *pointer,size_t old_size,size_t size) {
    Script *s=user; if(!pointer) old_size=0;
    if(!size) { free(pointer); s->memory-=old_size; return NULL; }
    if(size>SCRIPT_MEMORY_MAX||s->memory-old_size>SCRIPT_MEMORY_MAX-size) return NULL;
    void *next=realloc(pointer,size); if(!next) return NULL;
    s->memory=s->memory-old_size+size; if(s->memory>s->peak) s->peak=s->memory; return next;
}
static void instruction_hook(lua_State *L,lua_Debug *debug) {
    (void)debug; Script *s=context(L);
    if(s->instructions<=100) luaL_error(L,"Lua instruction budget exceeded");
    s->instructions-=100;
}
static void destroy(Script *s) { if(s) { if(s->lua) lua_close(s->lua); free(s); } }
static float number(lua_State *L,int index,float low,float high) {
    double value=luaL_checknumber(L,index);
    if(!isfinite(value)||value<low||value>high) luaL_error(L,"argument %d must be finite and in range",index);
    return (float)value;
}
static uint32_t color(lua_State *L,int index) {
    lua_Integer value=luaL_optinteger(L,index,0xffefefe8u);
    if(value<0||(uint64_t)value>UINT32_MAX) luaL_error(L,"color must be a uint32 from vita.rgb");
    return (uint32_t)value;
}
static Draw *drawing(lua_State *L,unsigned type) {
    Script *s=context(L);
    if(s->phase!=3) luaL_error(L,"drawing is available only inside draw()");
    if(s->draw_count>=SCRIPT_DRAW_MAX) luaL_error(L,"drawing budget exceeded (256 commands)");
    Draw *d=&s->drawing[s->draw_count++]; memset(d,0,sizeof(*d)); d->type=type; return d;
}
static int rectangle(lua_State *L) {
    Draw *d=drawing(L,1); d->values[0]=number(L,1,-960,1920); d->values[1]=number(L,2,-544,1088);
    d->values[2]=number(L,3,0,1920); d->values[3]=number(L,4,0,1088); d->color=color(L,5); return 0;
}
static int circle(lua_State *L) {
    Draw *d=drawing(L,2); d->values[0]=number(L,1,-960,1920); d->values[1]=number(L,2,-544,1088);
    d->values[2]=number(L,3,0,544); d->color=color(L,4); return 0;
}
static int line(lua_State *L) {
    Draw *d=drawing(L,3); d->values[0]=number(L,1,-960,1920); d->values[1]=number(L,2,-544,1088);
    d->values[2]=number(L,3,-960,1920); d->values[3]=number(L,4,-544,1088); d->color=color(L,5); return 0;
}
static int text(lua_State *L) {
    Draw *d=drawing(L,4); d->values[0]=number(L,1,-960,1920); d->values[1]=number(L,2,-544,1088);
    d->values[2]=number(L,3,0.25f,3); d->color=color(L,4);
    size_t size; const char *value=luaL_checklstring(L,5,&size);
    if(size>96) return luaL_error(L,"text is limited to 96 ASCII characters");
    for(size_t n=0;n<size;n++) if((unsigned char)value[n]<32||(unsigned char)value[n]>126) return luaL_error(L,"draw text must be printable ASCII");
    memcpy(d->text,value,size); d->text[size]=0; return 0;
}
static int rgb(lua_State *L) {
    unsigned r=(unsigned)number(L,1,0,255),g=(unsigned)number(L,2,0,255),b=(unsigned)number(L,3,0,255);
    lua_pushinteger(L,(lua_Integer)COLOR(r,g,b)); return 1;
}
static int log_message(lua_State *L) {
    Script *s=context(L); size_t size; const char *value=luaL_checklstring(L,1,&size);
    if(size>100) return luaL_error(L,"log message is limited to 100 bytes");
    if(s->log_count<8) clean_message(s->logs[s->log_count++],128,value);
    return 0;
}
static int metric(lua_State *L) {
    Script *s=context(L); size_t length; const char *name=luaL_checklstring(L,1,&length);
    if(!length||length>24) return luaL_error(L,"metric name must be 1..24 ASCII letters, digits or underscores");
    for(size_t n=0;n<length;n++) if(!((name[n]>='a'&&name[n]<='z')||(name[n]>='A'&&name[n]<='Z')||(name[n]>='0'&&name[n]<='9')||name[n]=='_')) return luaL_error(L,"invalid metric name");
    float value=number(L,2,-1e9f,1e9f); unsigned n;
    for(n=0;n<s->metric_count;n++) if(!strcmp(s->metrics[n].name,name)) break;
    if(n>=8) return luaL_error(L,"metric budget exceeded (8 names)");
    if(n==s->metric_count) s->metric_count++;
    snprintf(s->metrics[n].name,sizeof(s->metrics[n].name),"%s",name); s->metrics[n].value=value; return 0;
}
static void field_number(lua_State *L,const char *name,double value) { lua_pushnumber(L,isfinite(value)?value:0); lua_setfield(L,-2,name); }
static void field_int(lua_State *L,const char *name,lua_Integer value) { lua_pushinteger(L,value); lua_setfield(L,-2,name); }
static void panel(lua_State *L,const TouchPanel *p) {
    lua_createtable(L,p->count,1); field_int(L,"read_result",p->read_result);
    for(int n=0;n<p->count&&n<MAX_TOUCHES;n++) {
        const Contact *v=&p->points[n]; lua_createtable(L,0,5);
        field_int(L,"id",v->id); field_number(L,"x",v->x); field_number(L,"y",v->y);
        field_int(L,"raw_x",v->raw_x); field_int(L,"raw_y",v->raw_y); lua_rawseti(L,-2,n+1);
    }
}
static void push_input(lua_State *L,const Input *in) {
    lua_createtable(L,0,12); field_int(L,"buttons",in->buttons); field_int(L,"pressed",in->pressed);
    field_int(L,"controller_result",in->ctrl_result); field_int(L,"lx",in->lx); field_int(L,"ly",in->ly); field_int(L,"rx",in->rx); field_int(L,"ry",in->ry);
    field_number(L,"fps",in->fps); lua_pushboolean(L,in->resumed); lua_setfield(L,-2,"resumed");
    panel(L,&in->front); lua_setfield(L,-2,"front"); panel(L,&in->back); lua_setfield(L,-2,"rear");
    lua_createtable(L,0,7); field_int(L,"read_result",in->motion_result);
    field_number(L,"ax",in->acceleration.x); field_number(L,"ay",in->acceleration.y); field_number(L,"az",in->acceleration.z);
    field_number(L,"gx",in->gyro.x); field_number(L,"gy",in->gyro.y); field_number(L,"gz",in->gyro.z); lua_setfield(L,-2,"motion");
}
static void get_callback(lua_State *L,const char *name) {
    Script *s=context(L); lua_rawgeti(L,LUA_REGISTRYINDEX,s->callbacks); lua_getfield(L,-1,name); lua_remove(L,-2);
}
static int call_update(lua_State *L) {
    Script *s=context(L); s->phase=2; get_callback(L,"update");
    lua_pushnumber(L,fminf(fmaxf(s->input.dt,0),0.05f)); push_input(L,&s->input); lua_call(L,2,0); return 0;
}
static int call_draw(lua_State *L) {
    Script *s=context(L); s->phase=3; s->draw_count=0; get_callback(L,"draw"); lua_call(L,0,0); return 0;
}
static bool protected_call(Script *s,lua_CFunction function,unsigned budget) {
    s->instructions=budget; lua_sethook(s->lua,instruction_hook,LUA_MASKCOUNT,100);
    lua_pushcfunction(s->lua,function);
    int result=lua_pcall(s->lua,0,0,0); lua_sethook(s->lua,NULL,0,0); s->phase=0;
    if(result!=LUA_OK) { clean_message(s->error,sizeof(s->error),lua_tostring(s->lua,-1)); lua_settop(s->lua,0); s->faulted=true; return false; }
    lua_settop(s->lua,0); return true;
}
static int prepare(lua_State *L) {
    Script *s=context(L); s->phase=1;
    luaL_requiref(L,"_G",luaopen_base,1); lua_pop(L,1);
    luaL_requiref(L,"math",luaopen_math,1); lua_pop(L,1);
    luaL_requiref(L,"string",luaopen_string,1); lua_pop(L,1);
    luaL_requiref(L,"table",luaopen_table,1); lua_pop(L,1);
    luaL_requiref(L,"utf8",luaopen_utf8,1); lua_pop(L,1);
    const char *removed[]={"dofile","loadfile","load","collectgarbage","pcall","xpcall","setmetatable","getmetatable","warn","print"};
    for(unsigned n=0;n<sizeof(removed)/sizeof(removed[0]);n++) { lua_pushnil(L); lua_setglobal(L,removed[n]); }
    lua_getglobal(L,"string"); lua_pushnil(L); lua_setfield(L,-2,"dump"); lua_pop(L,1);
    lua_newtable(L);
    const luaL_Reg functions[]={{"rect",rectangle},{"circle",circle},{"line",line},{"text",text},{"rgb",rgb},{"log",log_message},{"metric",metric},{NULL,NULL}};
    luaL_setfuncs(L,functions,0); field_int(L,"width",SCREEN_W); field_int(L,"height",SCREEN_H);
    lua_newtable(L);
    const struct { const char *name; unsigned value; } buttons[]={
        {"SELECT",BTN_SELECT},{"START",BTN_START},{"UP",BTN_UP},{"RIGHT",BTN_RIGHT},{"DOWN",BTN_DOWN},{"LEFT",BTN_LEFT},
        {"L",BTN_L},{"R",BTN_R},{"TRIANGLE",BTN_TRIANGLE},{"CIRCLE",BTN_CIRCLE},{"CROSS",BTN_CROSS},{"SQUARE",BTN_SQUARE}};
    for(unsigned n=0;n<sizeof(buttons)/sizeof(buttons[0]);n++) field_int(L,buttons[n].name,buttons[n].value);
    lua_setfield(L,-2,"buttons"); lua_setglobal(L,"vita");
    char chunk[40]; snprintf(chunk,sizeof(chunk),"@%s.lua",s->name);
    if(luaL_loadbufferx(L,s->source,strlen(s->source),chunk,"t")!=LUA_OK) return lua_error(L);
    lua_call(L,0,1); luaL_checktype(L,-1,LUA_TTABLE);
    const char *required[]={"update","draw"};
    for(unsigned n=0;n<2;n++) { lua_getfield(L,-1,required[n]); if(!lua_isfunction(L,-1)) return luaL_error(L,"script must return a table with update(dt,input) and draw() functions"); lua_pop(L,1); }
    s->callbacks=luaL_ref(L,LUA_REGISTRYINDEX);
    get_callback(L,"init");
    if(lua_isnil(L,-1)) lua_pop(L,1);
    else { luaL_checktype(L,-1,LUA_TFUNCTION); lua_call(L,0,0); }
    return 0;
}
static Script *candidate(const char *name,const char *source,const char *sha256,const Input *input,char *error,size_t capacity) {
    if(!*name||strlen(name)>32) { snprintf(error,capacity,"Invalid script name"); return NULL; }
    for(const char *p=name;*p;p++) if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='_'||*p=='-')) { snprintf(error,capacity,"Invalid script name"); return NULL; }
    size_t bytes=strlen(source); char observed[65]; dev_sha256(source,bytes,observed);
    if(!bytes||bytes>SCRIPT_MAX||strcmp(observed,sha256)) { snprintf(error,capacity,"Script size or SHA-256 mismatch"); return NULL; }
    for(const unsigned char *p=(const unsigned char*)source;*p;p++) if(*p<32&&*p!='\n'&&*p!='\r'&&*p!='\t') { snprintf(error,capacity,"Script must be text, not bytecode"); return NULL; }
    Script *s=calloc(1,sizeof(*s));
    if(!s) { snprintf(error,capacity,"Script allocation failed"); return NULL; }
    snprintf(s->name,sizeof(s->name),"%s",name); memcpy(s->source,source,bytes+1); memcpy(s->sha256,sha256,65); s->input=*input;
    s->input.dt=0; s->input.pressed=0;
    s->lua=lua_newstate(allocate,s);
    if(!s->lua) { snprintf(error,capacity,"Lua state allocation failed"); destroy(s); return NULL; }
    *(Script**)lua_getextraspace(s->lua)=s;
    if(!protected_call(s,prepare,60000)||!protected_call(s,call_update,20000)||!protected_call(s,call_draw,20000)) {
        snprintf(error,capacity,"%s",s->error); destroy(s); return NULL;
    }
    return s;
}
void script_shutdown(void) { destroy(current); destroy(previous); current=previous=NULL; active=false; last_error[0]=0; }
bool script_load(const char *name,const char *source,const char *sha256,const Input *input,char *error,size_t capacity) {
    Script *next=candidate(name,source,sha256,input,error,capacity);
    if(!next) { snprintf(last_error,sizeof(last_error),"%s",error); return false; }
    destroy(previous); previous=current; current=next; active=true; last_error[0]=0; return true;
}
bool script_control(const char *action,const Input *input,char *error,size_t capacity) {
    if(!strcmp(action,"native")) { active=false; return true; }
    if(!current) { snprintf(error,capacity,"No Lua experiment is loaded"); return false; }
    if(!strcmp(action,"script_activate")) {
        if(current->faulted) { snprintf(error,capacity,"Lua experiment is faulted; restart, reload or roll back"); return false; }
        active=true; return true;
    }
    if(!strcmp(action,"script_rollback")) {
        if(!previous||previous->faulted) { snprintf(error,capacity,"No previous healthy Lua experiment is available"); return false; }
        Script *old=current; current=previous; previous=old; active=true; last_error[0]=0; return true;
    }
    if(!strcmp(action,"script_restart")) {
        Script *next=candidate(current->name,current->source,current->sha256,input,error,capacity);
        if(!next) { snprintf(last_error,sizeof(last_error),"%s",error); return false; }
        destroy(current); current=next; active=true; last_error[0]=0; return true;
    }
    snprintf(error,capacity,"Unknown script action"); return false;
}
bool script_frame(const Input *input,bool paused) {
    if(!active||!current||current->faulted) return true;
    current->input=*input;
    if(!paused) {
        clock_t started=clock(); bool ok=protected_call(current,call_update,20000);
        current->update_ms=(float)((double)(clock()-started)*1000/CLOCKS_PER_SEC);
        if(!ok) { snprintf(last_error,sizeof(last_error),"%s",current->error); return false; }
        current->updates++;
    }
    clock_t started=clock(); bool ok=protected_call(current,call_draw,20000);
    current->draw_ms=(float)((double)(clock()-started)*1000/CLOCKS_PER_SEC);
    if(!ok) { snprintf(last_error,sizeof(last_error),"%s",current->error); return false; }
    return true;
}
void script_render(void) {
    if(!active||!current||current->faulted) return;
    for(unsigned n=0;n<current->draw_count;n++) {
        Draw *d=&current->drawing[n]; float *v=d->values;
        if(d->type==1) draw_rect(v[0],v[1],v[2],v[3],d->color);
        if(d->type==2) draw_circle(v[0],v[1],v[2],d->color);
        if(d->type==3) draw_line(v[0],v[1],v[2],v[3],d->color);
        if(d->type==4) draw_text(v[0],v[1],v[2],d->color,d->text);
    }
}
void script_info(DevScriptInfo *out) {
    memset(out,0,sizeof(*out)); out->loaded=current!=NULL; out->active=active;
    out->rollback_available=previous&&!previous->faulted; snprintf(out->error,sizeof(out->error),"%s",last_error);
    if(current) {
        snprintf(out->name,sizeof(out->name),"%s",current->name); memcpy(out->sha256,current->sha256,65);
        out->faulted=current->faulted; out->source_bytes=(unsigned)strlen(current->source); out->updates=current->updates;
        out->draw_commands=current->draw_count; out->memory_bytes=(unsigned)current->memory; out->peak_memory_bytes=(unsigned)current->peak;
        out->update_ms=current->update_ms; out->draw_ms=current->draw_ms;
        out->metric_count=current->metric_count; memcpy(out->metrics,current->metrics,sizeof(out->metrics));
    }
    if(previous) { snprintf(out->previous_name,sizeof(out->previous_name),"%s",previous->name); memcpy(out->previous_sha256,previous->sha256,65); }
}
unsigned script_take_logs(char out[8][128]) {
    if(!active||!current) return 0;
    unsigned count=current->log_count; memcpy(out,current->logs,count*128); current->log_count=0; return count;
}
