#include "telemetry.h"
#include "protocol.h"
#include <psp2/kernel/threadmgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/sysmodule.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
static SceUID mutex=-1,thread=-1;
static int active,health,net_owned,ctl_owned;
static TargetState snapshot;
static char token[33],run[33];
static unsigned char net_memory[256*1024] __attribute__((aligned(16)));
static void lock(void) { sceKernelLockMutex(mutex,1,NULL); }
static void unlock(void) { sceKernelUnlockMutex(mutex,1); }
static int running(void) { return __atomic_load_n(&active,__ATOMIC_ACQUIRE); }
static uint64_t now(void) { return sceKernelGetProcessTimeWide()/1000; }
static int again(void) { int e=*sceNetErrnoLoc();return e==SCE_NET_EAGAIN||e==SCE_NET_EWOULDBLOCK; }
static int nb(int fd) { int on=1;return sceNetSetsockopt(fd,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on)); }
static int listen_socket(void) {
    int fd=sceNetSocket("input-target",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0);if(fd<0) return -1;
    SceNetSockaddrIn a={0};a.sin_len=sizeof(a);a.sin_family=SCE_NET_AF_INET;a.sin_port=sceNetHtons(17868);a.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    int yes=1;sceNetSetsockopt(fd,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&yes,sizeof(yes));
    if(nb(fd)<0||sceNetBind(fd,(SceNetSockaddr*)&a,sizeof(a))<0||sceNetListen(fd,2)<0) { sceNetSocketClose(fd);return -1; }return fd;
}
static int send_all(int fd,const char *p,size_t size,uint64_t deadline) {
    while(size&&running()&&now()<deadline) {
        int n=sceNetSend(fd,p,size,0);if(n>0) { p+=n;size-=n; }
        else if(n<0&&again()) sceKernelDelayThread(2000);else return 0;
    }return !size;
}
static void serve(int fd) {
    char request[2049],body[2048],header[256];size_t used=0;uint64_t deadline=now()+2000;
    while(used<2048&&running()&&now()<deadline) {
        int n=sceNetRecv(fd,request+used,2048-used,0);
        if(n>0) { used+=n;request[used]=0;if(strstr(request,"\r\n\r\n")) break; }
        else if(n<0&&again()) sceKernelDelayThread(2000);else break;
    }
    request[used]=0;int code=target_authorize(request,used,token),n;
    if(code==200) { TargetState s;lock();s=snapshot;unlock();n=target_json(&s,body,sizeof(body),sceKernelGetProcessId(),run,TARGET_BUILD_ID); }
    else n=snprintf(body,sizeof(body),"{\"error\":\"Request rejected\"}");
    if(n<0||(size_t)n>=sizeof(body)) return;
    int h=snprintf(header,sizeof(header),"HTTP/1.1 %d Result\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",code,n);
    deadline=now()+2000;if(h>0&&(size_t)h<sizeof(header)&&send_all(fd,header,h,deadline)) send_all(fd,body,n,deadline);
}
static int worker(unsigned args,void *arg) {
    (void)args;(void)arg;int listener=-1;
    while(running()) {
        int state=0;sceNetCtlInetGetState(&state);
        if(state!=SCE_NETCTL_STATE_CONNECTED) { if(listener>=0) sceNetSocketClose(listener);listener=-1;__atomic_store_n(&health,0,__ATOMIC_RELEASE);sceKernelDelayThread(100000);continue; }
        if(listener<0) { listener=listen_socket();__atomic_store_n(&health,listener<0?-1:1,__ATOMIC_RELEASE); }
        if(listener>=0) { int fd=sceNetAccept(listener,NULL,NULL);if(fd>=0) { if(nb(fd)>=0) serve(fd);sceNetSocketClose(fd); }else if(!again()) { sceNetSocketClose(listener);listener=-1; } }
        sceKernelDelayThread(10000);
    }
    if(listener>=0) sceNetSocketClose(listener);
    return 0;
}
int target_server_start(void) {
    int fd=sceIoOpen("ux0:data/vita-resident/bridge.cfg",SCE_O_RDONLY,0);if(fd<0) return -1;
    char pairing[34];int n=sceIoRead(fd,pairing,sizeof(pairing));sceIoClose(fd);
    if(n!=32&&(n!=33||pairing[32]!='\n')) return -2;
    for(unsigned i=0;i<32;i++) if(!((pairing[i]>='0'&&pairing[i]<='9')||(pairing[i]>='a'&&pairing[i]<='f'))) return -2;
    memcpy(token,pairing,32);token[32]=0;
    if(sceSysmoduleIsLoaded(SCE_SYSMODULE_NET)<0&&sceSysmoduleLoadModule(SCE_SYSMODULE_NET)<0) return -3;
    SceNetInitParam init={net_memory,sizeof(net_memory),0};int result=sceNetInit(&init);net_owned=result==0;
    if(result<0&&result!=(int)0x80410110) return -3;
    result=sceNetCtlInit();ctl_owned=result==0;if(result<0&&result!=(int)0x80412102) return -3;
    mutex=sceKernelCreateMutex("target-snapshot",0,0,NULL);if(mutex<0) return -4;
    snprintf(run,sizeof(run),"%016llx%016llx",(unsigned long long)sceKernelGetProcessTimeWide(),(unsigned long long)(unsigned)sceKernelGetProcessId());
    __atomic_store_n(&active,1,__ATOMIC_RELEASE);thread=sceKernelCreateThread("target-http",worker,0x60,32768,0,0,NULL);
    if(thread<0||sceKernelStartThread(thread,0,NULL)<0) { __atomic_store_n(&active,0,__ATOMIC_RELEASE);if(thread>=0) sceKernelDeleteThread(thread);thread=-1;return -5; }return 0;
}
void target_server_publish(const TargetState *s) { if(mutex>=0) { lock();snapshot=*s;unlock(); } }
void target_server_stop(void) {
    __atomic_store_n(&active,0,__ATOMIC_RELEASE);
    if(thread>=0) { sceKernelWaitThreadEnd(thread,NULL,NULL);sceKernelDeleteThread(thread);thread=-1; }
    if(mutex>=0) { sceKernelDeleteMutex(mutex);mutex=-1; }
    if(ctl_owned) sceNetCtlTerm();
    if(net_owned) sceNetTerm();
}
int target_server_health(void) { return __atomic_load_n(&health,__ATOMIC_ACQUIRE); }
