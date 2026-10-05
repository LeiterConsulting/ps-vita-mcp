#define PU_HOST_TEST
#include "pairing_ui.c"
#include <assert.h>
#include <stdio.h>
static uint64_t clock_ms;
static int random_return,rpc_return=200,rpc_calls,approve_in_poll;
static uint32_t random_value=7;
static const char *rpc_state="pending";
static char diagnostics[4097];static unsigned diagnostic_used;
static unsigned code_renders;
int sceKernelLockMutex(int a,int b,void *c){(void)a;(void)b;(void)c;return 0;}
int sceKernelUnlockMutex(int a,int b){(void)a;(void)b;return 0;}
uint64_t sceKernelGetSystemTimeWide(void){return clock_ms*1000;}
int sceKernelGetRandomNumber(void *out,unsigned n){assert(n==4);memcpy(out,&random_value,4);return random_return;}
int sceKernelDelayThread(unsigned n){clock_ms+=n/1000;return 0;}
int sceRtcSetTime64_t(SceDateTime *d,uint64_t s){(void)s;memset(d,0,sizeof(*d));return 0;}
int sceIoOpen(const char *p,int a,int b){(void)a;(void)b;assert(!strcmp(p,"ux0:data/vita-control/pairing-ui.log"));return 1;}
int sceIoRead(int fd,void *out,unsigned n){(void)fd;(void)out;(void)n;return -1;}
int sceIoWrite(int fd,const void *p,unsigned n){(void)fd;assert(n+diagnostic_used<sizeof(diagnostics));memcpy(diagnostics+diagnostic_used,p,n);diagnostic_used+=n;diagnostics[diagnostic_used]=0;return (int)n;}
int sceIoClose(int fd){(void)fd;return 0;}
int sceKernelCreateMutex(const char *a,int b,int c,void *d){(void)a;(void)b;(void)c;(void)d;return 1;}
int sceKernelCreateThread(const char *a,int (*b)(unsigned,void *),int c,unsigned d,int e,int f,void *g){(void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;return 1;}
int sceKernelStartThread(int a,unsigned b,void *c){(void)a;(void)b;(void)c;return 0;}
int sceKernelDeleteThread(int a){(void)a;return 0;}
int sceKernelWaitThreadEnd(int a,void *b,void *c){(void)a;(void)b;(void)c;return 0;}
int sceKernelDeleteMutex(int a){(void)a;return 0;}
int sceSysmoduleIsLoaded(int a){(void)a;return 0;}
int sceSysmoduleLoadModule(int a){(void)a;return 0;}
int sceNetInit(SceNetInitParam *a){(void)a;return 0;}
int sceNetTerm(void){return 0;}
void vita2d_pgf_draw_text(vita2d_pgf *f,int x,int y,unsigned c,float s,const char *t){(void)f;(void)x;(void)y;(void)c;(void)s;if(strlen(t)==6&&strspn(t,"0123456789")==6)code_renders++;}
const PCIO *pc_platform_io(void){return 0;}
int pc_call(const PCIO *io,unsigned port,const char token[33],const char *path,const char *body,char out[PR_JSON_MAX]){
    (void)io;(void)port;(void)token;(void)body;rpc_calls++;
    if(approve_in_poll&&!strcmp(path,"/pairing/ui/poll")){approve_in_poll=0;pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);}
    snprintf(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"approval_state\":\"%s\",\"client_name\":\"Fixture\",\"request_id\":\"11111111111111111111111111111111\",\"client_id\":\"22222222222222222222222222222222\",\"client_nonce\":\"33333333333333333333333333333333\",\"remaining_ms\":60000}",rpc_state);
    return rpc_return;
}
static void fresh(void){memset(&ui,0,sizeof(ui));memset(&approval_arm,0,sizeof(approval_arm));memset(diagnostics,0,sizeof(diagnostics));diagnostic_used=diagnostic_bytes=0;mutex=thread=1;initialized=1;clock_ms=1000;random_return=0;random_value=7;rpc_return=200;rpc_calls=approve_in_poll=code_renders=0;rpc_state="pending";ui.mode=1;ui.ready=1;strcpy(ui.state,"pending");strcpy(ui.request,"11111111111111111111111111111111");strcpy(ui.client,"22222222222222222222222222222222");strcpy(ui.nonce,"33333333333333333333333333333333");ui.deadline=clock_ms+60000;}
static void arm(void){pu_input(0,0,1);clock_ms+=600;}
int main(void){
    fresh();pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);assert(ui.command==NONE);arm();pu_input(SCE_CTRL_CROSS,0,1);assert(ui.command==NONE);puts("PASS held CROSS cannot approve");
    fresh();arm();pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);assert(ui.command==APPROVE&&!strcmp(ui.code,"000007"));rpc_state="approved";uint64_t next=0;assert(worker_step(&next));pu_draw(0);assert(code_renders==1);clock_ms+=600;assert(worker_step(&next));assert(!strcmp(ui.code,"000007"));assert(!strstr(diagnostics,"000007")&&!strstr(diagnostics,ui.digest));puts("PASS physical edge retains leading-zero code across successful approval and refresh; diagnostics exclude secrets");
    fresh();random_return=-123;arm();pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);assert(ui.fault&&!ui.ready&&!ui.code[0]);char error[160];strcpy(error,ui.message);next=0;assert(!worker_step(&next));assert(!strcmp(ui.message,error)&&rpc_calls==0);puts("PASS random-source failure stays visible and never submits approval");
    fresh();random_return=-123;arm();approve_in_poll=1;next=0;assert(worker_step(&next));assert(ui.fault&&!ui.ready&&!ui.code[0]);assert(strstr(ui.message,"Code generation failed"));assert(!worker_step(&next));puts("PASS in-flight stale poll cannot erase physical approval failure");
    fresh();arm();pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);rpc_return=403;next=0;assert(worker_step(&next));assert(ui.fault&&!ui.ready&&!ui.code[0]&&!ui.digest[0]);strcpy(error,ui.message);assert(!worker_step(&next)&&!strcmp(ui.message,error));puts("PASS rejected approval clears code and latches error until explicit retry");
    rpc_return=200;pu_input(SCE_CTRL_SQUARE,SCE_CTRL_SQUARE,1);assert(!ui.fault&&ui.command==OPEN);assert(worker_step(&next)&&ui.ready);puts("PASS explicit retry clears fault and reopens through native UI");
    fresh();arm();approve_in_poll=1;next=0;assert(worker_step(&next));assert(ui.command==APPROVE&&!strcmp(ui.code,"000007"));rpc_state="approved";assert(worker_step(&next));assert(ui.ready&&!strcmp(ui.code,"000007"));puts("PASS approval during poll keeps command and verifier bound to new revision");
    fresh();arm();ui.deadline=clock_ms;pu_input(SCE_CTRL_CROSS,SCE_CTRL_CROSS,1);assert(ui.fault&&!ui.code[0]&&ui.command==NONE);puts("PASS expired local deadline cannot generate or submit code");
    int result;char code[7];random_value=999999;assert(pu_code(rng,code,&result)&&!strcmp(code,"999999"));random_value=0;assert(pu_code(rng,code,&result)&&!strcmp(code,"000000"));random_value=4294000000u;assert(!pu_code(rng,code,&result)&&!code[0]);puts("PASS decimal boundaries and unbiased rejection cap");
    return 0;
}
