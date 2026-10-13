#include "../platform.h"
#include "policy.h"
#include "power_platform.h"
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
static SceUID power_thread=-1;
static void (*power_worker)(void);
uint64_t rkap_now(void) { return sceKernelGetSystemTimeWide()/1000; }
int rkap_tick(void) { return sceKernelPowerTick(SCE_KERNEL_POWER_TICK_DISABLE_AUTO_SUSPEND); }
RKANetworkResult rkap_network(void) { RKANetworkResult result={0,-1};result.result=sceNetCtlInetGetState(&result.state);return result; }
static void captured(RKASocketResult *out,int stage,int raw) {
    int error=raw<0?*sceNetErrnoLoc():0;
    out->result=raw;out->error=error;out->stage=stage;
}
static int would_block(const RKASocketResult *out) { return out->error==SCE_NET_EAGAIN||out->error==SCE_NET_EWOULDBLOCK; }
static void cleanup(int socket,RKASocketResult *out) {
    int raw=sceNetSocketClose(socket);int error=raw<0?*sceNetErrnoLoc():0;
    out->close_result=raw;out->close_error=error;
}
int rkap_close(int socket,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));int raw=sceNetSocketClose(socket);captured(out,RKA_STAGE_CLOSE,raw);return raw;
}
int rkap_accept(int socket,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));int client=sceNetAccept(socket,0,0);captured(out,RKA_STAGE_ACCEPT,client);
    if(client<0) return would_block(out)?-1:-2;
    int on=1,raw=sceNetSetsockopt(client,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on));
    if(raw<0) { captured(out,RKA_STAGE_CLIENT_NBIO,raw);cleanup(client,out);return -1; }
    return client;
}
int rkap_recv(int socket,void *data,size_t size,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));int raw=sceNetRecv(socket,data,size,0);captured(out,RKA_STAGE_RECV,raw);
    return raw<0&&would_block(out)?-2:raw;
}
int rkap_send(int socket,const void *data,size_t size,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));int raw=sceNetSend(socket,data,size,0);captured(out,RKA_STAGE_SEND,raw);
    return raw<0&&would_block(out)?-2:raw;
}
int rkap_listen(RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));
    int socket=sceNetSocket("resident-keep-awake",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0);
    captured(out,RKA_STAGE_SOCKET,socket);
    if(socket<0) return socket;
    int yes=1;
    RKASocketResult reuse={0};
    int raw=sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&yes,sizeof(yes));captured(&reuse,RKA_STAGE_REUSE,raw);
    SceNetSockaddrIn address={0};address.sin_len=sizeof(address);address.sin_family=SCE_NET_AF_INET;
    address.sin_port=sceNetHtons(RKA_PORT);address.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    raw=sceNetBind(socket,(SceNetSockaddr *)&address,sizeof(address));captured(out,RKA_STAGE_BIND,raw);
    if(raw<0) { cleanup(socket,out);return -1; }
    raw=sceNetListen(socket,4);captured(out,RKA_STAGE_LISTEN,raw);
    if(raw<0) { cleanup(socket,out);return -1; }
    raw=sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&yes,sizeof(yes));captured(out,RKA_STAGE_LISTENER_NBIO,raw);
    if(raw<0) { cleanup(socket,out);return -1; }
    /* REUSEADDR was historically best-effort; retain evidence, not a new failure policy. */
    if(reuse.result<0) *out=reuse;
    return socket;
}
static int worker_entry(unsigned args,void *arg) { (void)args;(void)arg;power_worker();return 0; }
int rkap_worker_start(void (*worker)(void)) {
    if(power_thread>=0) return -1;
    power_worker=worker;
    /* 0x40 is the highest user priority; 0x38 fails with ILLEGAL_PRIORITY. */
    power_thread=sceKernelCreateThread("resident-keep-awake",worker_entry,0x40,32768,0,0,0);
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
