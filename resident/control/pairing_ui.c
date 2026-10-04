#include "pairing_ui.h"
#include "pairing_client.h"
#include "platform.h"
#include "pairing_approval.h"
#include <psp2/ctrl.h>
#include <psp2/kernel/rng.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/net/net.h>
#include <psp2/sysmodule.h>
#include <psp2/rtc.h>
#define INK(r,g,b) ((unsigned)(r)|((unsigned)(g)<<8)|((unsigned)(b)<<16)|0xff000000u)
enum { NONE, OPEN, APPROVE, CLOSE, LIST, REVOKE };
typedef struct {char id[33],name[65];uint64_t seen,expires;int revoked;} Phone;
typedef struct {
    int mode,command,ready,selected,count;unsigned revision;
    char state[24],name[65],request[33],client[33],nonce[33],code[7],digest[65],message[160];
    uint64_t deadline;
    Phone phones[PR_MAX_PHONES];
} UI;
static UI ui;
static SceUID mutex=-1,thread=-1;
static volatile int running;
static char admin[33];
static unsigned char net_memory[128*1024] __attribute__((aligned(16)));
static int network_owned,initialized;
static PAArm approval_arm;
static void lock(void){sceKernelLockMutex(mutex,1,0);}
static void unlock(void){sceKernelUnlockMutex(mutex,1);}
static uint64_t now(void){return sceKernelGetSystemTimeWide()/1000;}
static int rng(void *out,size_t n){return n<=64?sceKernelGetRandomNumber(out,(unsigned)n):-1;}
static int hex32(const char *p){if(R_STRLEN(p)!=32)return 0;for(unsigned i=0;i<32;i++)if(!((p[i]>='0'&&p[i]<='9')||(p[i]>='a'&&p[i]<='f')))return 0;return 1;}
static void clear_code(UI *v){R_MEMSET(v->code,0,sizeof(v->code));R_MEMSET(v->digest,0,sizeof(v->digest));}
static void message(UI *v,const char *text){R_SNPRINTF(v->message,sizeof(v->message),"%s",text);}
static void date_text(uint64_t seconds,char out[40]) {
    SceDateTime date={0};if(sceRtcSetTime64_t(&date,seconds)<0){R_SNPRINTF(out,40,"unavailable");return;}
    R_SNPRINTF(out,40,"%04u-%02u-%02u %02u:%02u UTC",date.year,date.month,date.day,date.hour,date.minute);
}
static int poll_reply(UI *v,const char *json) {
    size_t n=R_STRLEN(json);uint64_t remaining=0;char app[32];uint64_t protocol=0;
    if(!pr_json_string(json,n,"app",app,sizeof(app))||R_STRCMP(app,"Vita Companion Pairing")||!pr_json_uint(json,n,"protocol",&protocol)||protocol!=1||
       !pr_json_string(json,n,"approval_state",v->state,sizeof(v->state))||!pr_json_string(json,n,"client_name",v->name,sizeof(v->name))||
       !pr_json_string(json,n,"request_id",v->request,sizeof(v->request))||!pr_json_string(json,n,"client_id",v->client,sizeof(v->client))||
       !pr_json_string(json,n,"client_nonce",v->nonce,sizeof(v->nonce))||!pr_json_uint(json,n,"remaining_ms",&remaining)||remaining>120000)return 0;
    if(R_STRCMP(v->state,"none")&&(!hex32(v->request)||!hex32(v->client)||!hex32(v->nonce)))return 0;
    v->deadline=now()+remaining;
    if(R_STRCMP(v->state,"approved"))clear_code(v);
    v->ready=1;
    if(!R_STRCMP(v->state,"none"))message(v,"Choose Pair a Vita on your phone. This window lasts two minutes.");
    else if(!R_STRCMP(v->state,"pending"))message(v,"CROSS: approve this phone. CIRCLE: reject and close.");
    else if(!R_STRCMP(v->state,"approved"))message(v,"Enter the code on this phone before the countdown ends.");
    else if(!R_STRCMP(v->state,"complete"))message(v,"Phone paired. CIRCLE: return. SQUARE: pair another phone.");
    else message(v,"Request ended. SQUARE: open a new window. CIRCLE: return.");
    return 1;
}
static int list_reply(UI *v,const char *json) {
    char object[768];v->count=0;
    for(unsigned i=0;i<PR_MAX_PHONES;i++){
        if(!pr_json_object_at(json,R_STRLEN(json),"phones",i,object,sizeof(object)))break;
        Phone *p=&v->phones[v->count];size_t n=R_STRLEN(object);
        if(!pr_json_string(object,n,"credential_id",p->id,sizeof(p->id))||!hex32(p->id)||!pr_json_string(object,n,"client_name",p->name,sizeof(p->name))||
           !pr_json_uint(object,n,"last_seen_at",&p->seen)||!pr_json_uint(object,n,"expires_at",&p->expires)||!pr_json_bool(object,n,"revoked",&p->revoked))return 0;
        v->count++;
    }
    if(v->selected>=v->count)v->selected=0;
    v->ready=1;message(v,"UP/DOWN: select. CROSS: forget phone. CIRCLE: return.");return 1;
}
static int worker(unsigned args,void *arg) {
    (void)args;(void)arg;uint64_t next_poll=0;
    while(__atomic_load_n(&running,__ATOMIC_ACQUIRE)) {
        lock();UI current=ui;int command=ui.command;ui.command=NONE;unlock();
        if(!command&&current.mode==1&&current.ready&&now()>=next_poll)command=NONE;
        else if(!command){sceKernelDelayThread(20000);continue;}
        const char *path="/pairing/ui/poll";char body[512]="{\"protocol\":1}",reply[PR_JSON_MAX];
        if(command==OPEN){path="/pairing/ui/open";R_SNPRINTF(body,sizeof(body),"{\"protocol\":1,\"control_build_id\":\"%s\"}",R_BUILD_ID);}
        else if(command==CLOSE)path="/pairing/ui/close";
        else if(command==LIST){pc_call(pc_platform_io(),17866,admin,"/pairing/ui/close",body,reply);path="/pairing/ui/list";}
        else if(command==APPROVE){path="/pairing/ui/approve";R_SNPRINTF(body,sizeof(body),"{\"protocol\":1,\"request_id\":\"%s\",\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"code_sha256\":\"%s\"}",current.request,current.client,current.nonce,current.digest);}
        else if(command==REVOKE){path="/pairing/ui/revoke";R_SNPRINTF(body,sizeof(body),"{\"protocol\":1,\"credential_id\":\"%s\"}",current.phones[current.selected].id);}
        int result=pc_call(pc_platform_io(),17866,admin,path,body,reply);
        if(result==200&&command==REVOKE){current.mode=2;result=pc_call(pc_platform_io(),17866,admin,"/pairing/ui/list","{\"protocol\":1}",reply);}
        int good=result==200&&(command==CLOSE||(current.mode==2?list_reply(&current,reply):poll_reply(&current,reply)));
        if(!good){clear_code(&current);current.ready=0;message(&current,"Pairing unavailable. CIRCLE: return; check the Resident service.");}
        lock();if(ui.revision==current.revision){int waiting=ui.command;ui=current;ui.command=waiting;}unlock();
        R_MEMSET(body,0,sizeof(body));R_MEMSET(reply,0,sizeof(reply));R_MEMSET(&current,0,sizeof(current));next_poll=now()+500;
    }
    char reply[PR_JSON_MAX];pc_call(pc_platform_io(),17866,admin,"/pairing/ui/close","{\"protocol\":1}",reply);R_MEMSET(reply,0,sizeof(reply));return 0;
}
void pu_init(void) {
    mutex=sceKernelCreateMutex("pairing-ui",0,0,0);if(mutex<0)return;
    int fd=sceIoOpen("ux0:data/vita-resident/bridge.cfg",SCE_O_RDONLY,0);char bytes[34]={0};int n=fd>=0?sceIoRead(fd,bytes,sizeof(bytes)):-1;int closed=fd>=0?sceIoClose(fd):-1;
    if((n!=32&&!(n==33&&bytes[32]=='\n'))||closed<0){message(&ui,"Resident pairing configuration unavailable.");return;}
    bytes[32]=0;if(!hex32(bytes)){R_MEMSET(bytes,0,sizeof(bytes));return;}R_MEMCPY(admin,bytes,33);R_MEMSET(bytes,0,sizeof(bytes));
    initialized=1;
}
static int start_worker(void) {
    if(thread>=0)return 1;
    if(!initialized)return 0;
    if(sceSysmoduleIsLoaded(SCE_SYSMODULE_NET)<0&&sceSysmoduleLoadModule(SCE_SYSMODULE_NET)<0)return 0;
    SceNetInitParam init={net_memory,sizeof(net_memory),0};if(sceNetInit(&init)<0)return 0;network_owned=1;
    __atomic_store_n(&running,1,__ATOMIC_RELEASE);thread=sceKernelCreateThread("pairing-ui",worker,0x40,64*1024,0,0,0);
    if(thread<0||sceKernelStartThread(thread,0,0)<0){if(thread>=0)sceKernelDeleteThread(thread);thread=-1;__atomic_store_n(&running,0,__ATOMIC_RELEASE);sceNetTerm();network_owned=0;return 0;}return 1;
}
int pu_active(void){if(mutex<0)return 0;lock();int mode=ui.mode;unlock();return mode!=0;}
void pu_input(unsigned held,unsigned pressed,int valid) {
    if(mutex<0)return;
    if(pressed&(SCE_CTRL_SQUARE|SCE_CTRL_TRIANGLE)){int available=start_worker();lock();clear_code(&ui);ui.mode=(pressed&SCE_CTRL_TRIANGLE)?2:1;ui.command=available?(ui.mode==2?LIST:OPEN):NONE;ui.ready=0;ui.revision++;message(&ui,available?"Connecting to Resident...":"Pairing unavailable. CIRCLE: return.");unlock();return;}
    lock();
    int approved=pa_cross(&approval_arm,now(),ui.ready&&((ui.mode==1&&!R_STRCMP(ui.state,"pending"))||ui.mode==3),valid,held,pressed,SCE_CTRL_CROSS);
    if(ui.mode&&pressed&SCE_CTRL_CIRCLE){ui.mode=0;clear_code(&ui);ui.command=thread>=0?CLOSE:NONE;ui.revision++;}
    else if(approved&&ui.mode==1) {
        if(ui.deadline>now()&&pr_random_code(rng,ui.code)){pr_code_digest(ui.request,ui.client,ui.nonce,ui.code,ui.digest);ui.command=APPROVE;ui.ready=0;ui.revision++;message(&ui,"Recording physical approval...");}
        else{clear_code(&ui);message(&ui,"Request expired or random source unavailable.");}
    } else if(ui.mode==2&&ui.ready&&ui.count) {
        if(pressed&SCE_CTRL_DOWN)ui.selected=(ui.selected+1)%ui.count;
        if(pressed&SCE_CTRL_UP)ui.selected=(ui.selected+ui.count-1)%ui.count;
        if(pressed&SCE_CTRL_CROSS){ui.mode=3;ui.revision++;message(&ui,"Forget this phone? CROSS: confirm. CIRCLE: cancel.");}
    } else if(ui.mode==3&&approved){ui.command=REVOKE;ui.mode=2;ui.ready=0;ui.revision++;message(&ui,"Forgetting phone...");}
    unlock();
}
void pu_draw(vita2d_pgf *font) {
    if(mutex<0)return;
    lock();UI view=ui;unlock();
    vita2d_pgf_draw_text(font,30,45,INK(64,220,191),1.2f,view.mode==1?"PAIR A PHONE":"PAIRED PHONES");
    vita2d_pgf_draw_text(font,30,95,INK(210,221,239),1.0f,"Physical controls approve pairing. Screen capture is protected.");
    if(view.mode==1) {
        vita2d_pgf_draw_text(font,30,165,INK(255,197,98),1.1f,view.name);
        if(view.code[0]&&view.ready&&view.deadline>now()&&!R_STRCMP(view.state,"approved")) {
            vita2d_pgf_draw_text(font,30,255,INK(255,255,255),2.5f,view.code);char count[64];R_SNPRINTF(count,sizeof(count),"%llu seconds remaining",(unsigned long long)((view.deadline-now()+999)/1000));vita2d_pgf_draw_text(font,30,305,INK(210,221,239),1.0f,count);
        }
    } else if(view.ready||view.mode==3) {
        if(!view.count)vita2d_pgf_draw_text(font,30,165,INK(210,221,239),1.0f,"No paired phones.");
        for(int i=0;i<view.count;i++){char line[256];Phone *p=&view.phones[i];R_SNPRINTF(line,sizeof(line),"%s %s%s",i==view.selected?">":" ",p->name,p->revoked?" (forgotten)":"");vita2d_pgf_draw_text(font,30,150+i*30,INK(210,221,239),.9f,line);}
        if(view.count){char line[192],seen[40],expires[40];Phone *p=&view.phones[view.selected];date_text(p->seen,seen);date_text(p->expires,expires);R_SNPRINTF(line,sizeof(line),"Seen: %s   Expires: %s",seen,expires);vita2d_pgf_draw_text(font,30,420,INK(151,170,195),.8f,line);}
    }
    vita2d_pgf_draw_text(font,30,465,INK(255,197,98),.85f,view.message);
    vita2d_pgf_draw_text(font,30,505,INK(210,221,239),.9f,"SQUARE: pair phone   TRIANGLE: paired phones   START + SELECT: exit");
    R_MEMSET(&view,0,sizeof(view));
}
void pu_shutdown(void) {
    if(mutex<0)return;
    lock();clear_code(&ui);ui.mode=0;unlock();__atomic_store_n(&running,0,__ATOMIC_RELEASE);
    if(thread>=0){sceKernelWaitThreadEnd(thread,0,0);sceKernelDeleteThread(thread);thread=-1;}
    R_MEMSET(admin,0,sizeof(admin));if(network_owned)sceNetTerm();sceKernelDeleteMutex(mutex);mutex=-1;
}
