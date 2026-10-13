#include "lab_platform.h"
#include "lab_core.h"
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/rng.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/sysmodule.h>
#include <stdio.h>
#include <string.h>

static SceUID mutex=-1,thread=-1;
static int net_owned,ctl_owned,module_owned;
static int (*work)(void);
static unsigned char pool[256*1024] __attribute__((aligned(16)));
uint64_t lp_now(void){return sceKernelGetSystemTimeWide()/1000;}
void lp_delay(unsigned ms){sceKernelDelayThread(ms*1000);}
int lp_pid(void){return sceKernelGetProcessId();}
int lp_nonce(unsigned char nonce[16]){return sceKernelGetRandomNumber(nonce,16)==0;}
void lp_lock(void){sceKernelLockMutex(mutex,1,0);}
void lp_unlock(void){sceKernelUnlockMutex(mutex,1);}
int lp_init(void){
    mutex=sceKernelCreateMutex("lifecycle-lab",0,0,0);if(mutex<0)return -1;
    if(sceSysmoduleIsLoaded(SCE_SYSMODULE_NET)<0){if(sceSysmoduleLoadModule(SCE_SYSMODULE_NET)<0)goto fail;module_owned=1;}
    SceNetInitParam param={pool,sizeof(pool),0};int result=sceNetInit(&param);
    net_owned=result==0;
    if(result<0&&result!=(int)SCE_NET_ERROR_EBUSY)goto fail;
    result=sceNetCtlInit();ctl_owned=result==0;
    if(result<0&&result!=(int)0x80412102)goto fail;
    return 0;
fail:
    lp_end();return -1;
}
void lp_end(void){
    if(ctl_owned){sceNetCtlTerm();ctl_owned=0;}
    if(net_owned){sceNetTerm();net_owned=0;}
    if(module_owned){sceSysmoduleUnloadModule(SCE_SYSMODULE_NET);module_owned=0;}
    if(mutex>=0){sceKernelDeleteMutex(mutex);mutex=-1;}
}
int lp_token(char token[33]){
    FILE *file=fopen("ux0:data/vita-resident/bridge.cfg","rb");if(!file)return 0;
    char raw[35]={0};size_t n=fread(raw,1,sizeof(raw),file);int ok=fclose(file)==0;
    if(!ok||(n!=32&&!(n==33&&raw[32]=='\n')))return 0;
    for(unsigned i=0;i<32;i++)if(!((raw[i]>='0'&&raw[i]<='9')||(raw[i]>='a'&&raw[i]<='f')))return 0;
    memcpy(token,raw,32);token[32]=0;memset(raw,0,sizeof(raw));return 1;
}
static int nonblocking(int socket){int on=1;return sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on));}
static int again(void){int error=*sceNetErrnoLoc();return error==SCE_NET_EAGAIN||error==SCE_NET_EWOULDBLOCK;}
int lp_listen(void){
    int socket=sceNetSocket("lifecycle-lab",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0);if(socket<0)return socket;
    int reuse=1;sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&reuse,sizeof(reuse));
    SceNetSockaddrIn address={0};address.sin_len=sizeof(address);address.sin_family=SCE_NET_AF_INET;
    address.sin_port=sceNetHtons(LAB_PORT);address.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    if(sceNetBind(socket,(SceNetSockaddr *)&address,sizeof(address))<0||sceNetListen(socket,2)<0||nonblocking(socket)<0){sceNetSocketClose(socket);return -1;}
    return socket;
}
int lp_accept(int socket){int client=sceNetAccept(socket,0,0);if(client>=0&&nonblocking(client)<0){sceNetSocketClose(client);return -1;}return client;}
int lp_recv(int socket,void *data,size_t size){int n=sceNetRecv(socket,data,size,0);return n<0&&again()?-2:n;}
int lp_send(int socket,const void *data,size_t size){int n=sceNetSend(socket,data,size,0);return n<0&&again()?-2:n;}
int lp_close(int socket){return sceNetSocketClose(socket);}
static int thread_entry(SceSize args,void *arg){(void)args;(void)arg;return work();}
int lp_thread_start(int (*worker)(void)){
    work=worker;thread=sceKernelCreateThread("lifecycle-lab-http",thread_entry,0x40,64*1024,0,0,0);
    if(thread<0)return thread;
    int result=sceKernelStartThread(thread,0,0);
    if(result<0){sceKernelDeleteThread(thread);thread=-1;}return result;
}
int lp_thread_join(void){
    if(thread<0)return 0;
    SceUInt timeout=5000000;int result=sceKernelWaitThreadEnd(thread,0,&timeout);
    if(result>=0){sceKernelDeleteThread(thread);thread=-1;}return result;
}
