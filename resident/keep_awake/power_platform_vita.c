#include "../platform.h"
#include "policy.h"
#include "power_platform.h"
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/net/net.h>
static SceUID power_thread=-1;
static void (*power_worker)(void);
uint64_t rkap_now(void) { return sceKernelGetSystemTimeWide()/1000; }
int rkap_tick(void) { return sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND); }
int rkap_listen(void) {
    int socket=sceNetSocket("resident-keep-awake",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0);
    if(socket<0) return socket;
    int yes=1;
    sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&yes,sizeof(yes));
    SceNetSockaddrIn address={0};address.sin_len=sizeof(address);address.sin_family=SCE_NET_AF_INET;
    address.sin_port=sceNetHtons(RKA_PORT);address.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    if(sceNetBind(socket,(SceNetSockaddr *)&address,sizeof(address))<0||sceNetListen(socket,4)<0||
       sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&yes,sizeof(yes))<0) {
        sceNetSocketClose(socket);return -1;
    }
    return socket;
}
static int worker_entry(unsigned args,void *arg) { (void)args;(void)arg;power_worker();return 0; }
int rkap_worker_start(void (*worker)(void)) {
    if(power_thread>=0) return -1;
    power_worker=worker;
    /* A bounded worker must preempt Resident's 0x40 bulk-transfer thread. */
    power_thread=sceKernelCreateThread("resident-keep-awake",worker_entry,0x38,32768,0,0,0);
    if(power_thread<0) return power_thread;
    int result=sceKernelStartThread(power_thread,0,0);
    if(result<0) { sceKernelDeleteThread(power_thread);power_thread=-1; }
    return result;
}
int rkap_worker_join(void) {
    if(power_thread<0) return 0;
    SceUInt timeout=2000000;
    int result=sceKernelWaitThreadEnd(power_thread,0,&timeout);
    if(result<0) return result;
    result=sceKernelDeleteThread(power_thread);
    if(result>=0) power_thread=-1;
    return result;
}
