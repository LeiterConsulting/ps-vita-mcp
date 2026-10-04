#include "platform.h"
#include <psp2/kernel/modulemgr.h>
#include <psp2/kernel/rng.h>
#include <psp2/rtc.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/threadmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/power.h>
#include <psp2/sysmodule.h>

static volatile int running;
static int network_owned;
static SceUID thread=-1;
static char pairing[33];
static unsigned char net_memory[256*1024] __attribute__((aligned(16)));
static unsigned log_bytes;
/* Compiler-generated aggregate clearing must not depend on SceShell having libc. */
void *memset(void *destination,int value,size_t size) { return sceClibMemset(destination,value,size); }
void *memcpy(void *destination,const void *source,size_t size) { return sceClibMemcpy(destination,source,size); }

uint64_t r_pair_mono(void) { return sceKernelGetSystemTimeWide()/1000; }
int r_pair_utc(uint64_t *out) { SceDateTime date={0};SceUInt64 value=0;if(sceRtcGetCurrentClock(&date,0)<0||sceRtcGetTime64_t(&date,&value)<0)return -1;*out=value;return 0; }
int r_pair_random(void *out,size_t bytes) { return bytes<=64?sceKernelGetRandomNumber(out,(SceSize)bytes):-1; }
int r_pair_exists(const char *path) {SceIoStat stat={0};int r=sceIoGetstat(path,&stat);return r>=0?1:r==(int)0x80010002u?0:-1;}
int r_pair_remove(const char *path) {return sceIoRemove(path);}
int r_pair_sync_file(int fd) {return sceIoSyncByFd(fd,0);}
int r_pair_sync_device(void) {return sceIoSync("ux0:",0);}
int r_peer_loopback(int socket) {SceNetSockaddrIn a={0};unsigned size=sizeof(a);return sceNetGetpeername(socket,(SceNetSockaddr *)&a,&size)>=0&&a.sin_family==SCE_NET_AF_INET&&sceNetNtohl(a.sin_addr.s_addr)==0x7f000001u;}
uint64_t r_now(void) { return sceKernelGetProcessTimeWide()/1000; }
void r_delay(unsigned ms) { sceKernelDelayThread(ms*1000); }
int r_running(void) { return __atomic_load_n(&running,__ATOMIC_ACQUIRE); }
void r_log(const char *message,int result) {
    if(log_bytes>=2048) return;
    char line[192]; int n=R_SNPRINTF(line,sizeof(line),"tick_ms=%llu %s result=0x%08x\n",(unsigned long long)r_now(),message,(unsigned)result);
    if(n<=0||(unsigned)n>=sizeof(line)||log_bytes+(unsigned)n>2048) return;
    int fd=sceIoOpen("ux0:data/vita-resident/startup.log",SCE_O_WRONLY|SCE_O_CREAT|SCE_O_APPEND,(0600 | SCE_S_IWSYS | SCE_S_IRSYS));
    if(fd>=0) { sceIoWrite(fd,line,(unsigned)n); sceIoClose(fd); log_bytes+=(unsigned)n; }
}
int r_network_init(void) {
    if(sceSysmoduleIsLoaded(SCE_SYSMODULE_NET)<0) {
        int result=sceSysmoduleLoadModule(SCE_SYSMODULE_NET); r_log("Net module load",result); if(result<0) return result;
    }
    SceNetInitParam init={net_memory,sizeof(net_memory),0};
    int result=sceNetInit(&init); network_owned=result==0; r_log("Net init (existing state may be borrowed)",result);
    result=sceNetCtlInit(); r_log("NetCtl init",result);
    if(result<0&&result!=(int)0x80412102) return result;
    return 0;
}
int r_network_ready(void) { int state=0; return sceNetCtlInetGetState(&state)>=0&&state==SCE_NETCTL_STATE_CONNECTED; }
void r_network_end(void) {
    /* SceShell networking is shared with other plugins. Never terminate it here.
       If we supplied the pool, module_stop refuses unloading it; reboot ends it. */
}
static int nonblocking(int socket) { int on=1; return sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on)); }
static int again(void) { int error=*sceNetErrnoLoc(); return error==SCE_NET_EAGAIN||error==SCE_NET_EWOULDBLOCK; }
int r_listen(void) {
    int socket=sceNetSocket("vita-resident",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0); if(socket<0) return socket;
    int reuse=1; sceNetSetsockopt(socket,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&reuse,sizeof(reuse));
    SceNetSockaddrIn address={0}; address.sin_len=sizeof(address); address.sin_family=SCE_NET_AF_INET;
    address.sin_port=sceNetHtons(R_PORT); address.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    if(sceNetBind(socket,(SceNetSockaddr *)&address,sizeof(address))<0||sceNetListen(socket,2)<0||nonblocking(socket)<0) { sceNetSocketClose(socket); return -1; }
    return socket;
}
int r_accept(int socket) { int client=sceNetAccept(socket,0,0); if(client<0) return again()?-1:-2; if(nonblocking(client)<0) { sceNetSocketClose(client); return -1; } return client; }
int r_recv(int socket,void *data,size_t size) { int n=sceNetRecv(socket,data,size,0); return n<0&&again()?-2:n; }
int r_send(int socket,const void *data,size_t size) { int n=sceNetSend(socket,data,size,0); return n<0&&again()?-2:n; }
void r_close_socket(int socket) { sceNetSocketClose(socket); }
void r_device(RDevice *d) {
    d->battery=scePowerGetBatteryLifePercent(); d->charging=scePowerIsBatteryCharging();
    d->cpu=scePowerGetArmClockFrequency(); d->bus=scePowerGetBusClockFrequency(); d->gpu=scePowerGetGpuClockFrequency(); d->xbar=scePowerGetGpuXbarClockFrequency();
    d->network=-1; sceNetCtlInetGetState(&d->network);
}
/* UNSAFE user modules must request the system RW bits explicitly. */
int r_dir(const char *path) { return sceIoMkdir(path,(0700 | SCE_S_IWSYS | SCE_S_IRSYS)); }
int r_directory_exists(const char *path) { SceIoStat stat={0}; return sceIoGetstat(path,&stat)>=0&&SCE_S_ISDIR(stat.st_mode); }
int r_open_write(const char *path) { return sceIoOpen(path,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,(0600 | SCE_S_IWSYS | SCE_S_IRSYS)); }
int r_open_read(const char *path) { return sceIoOpen(path,SCE_O_RDONLY,0); }
int r_write(int fd,const void *data,size_t size) { return sceIoWrite(fd,data,size); }
int r_read(int fd,void *data,size_t size) { return sceIoRead(fd,data,size); }
int r_close_file(int fd) { return sceIoClose(fd); }
int r_file_size(const char *path,uint64_t *size) { SceIoStat stat={0}; int result=sceIoGetstat(path,&stat); if(result<0||!SCE_S_ISREG(stat.st_mode)||stat.st_size<0) return -1; *size=(uint64_t)stat.st_size; return 0; }
int r_rename(const char *from,const char *to) { SceIoStat stat={0}; if(sceIoGetstat(to,&stat)>=0) return -1; return sceIoRename(from,to); }
static int worker(unsigned args,void *arg) { (void)args; (void)arg; r_delay(3000); if(r_running()) r_service(pairing); return 0; }
int _start(SceSize args,const void *arg) __attribute__((weak,alias("module_start")));
int module_start(SceSize args,const void *arg) {
    (void)args; (void)arg;
    int fd=sceIoOpen("ux0:data/vita-resident/startup.log",SCE_O_WRONLY|SCE_O_CREAT|SCE_O_TRUNC,(0600 | SCE_S_IWSYS | SCE_S_IRSYS)); if(fd>=0) sceIoClose(fd); log_bytes=0;
    fd=r_open_read("ux0:data/vita-resident/bridge.cfg"); if(fd<0) { r_log("pairing file missing",fd); return SCE_KERNEL_START_FAILED; }
    char data[34]={0}; int n=r_read(fd,data,sizeof(data)); r_close_file(fd);
    if(n!=32&&!(n==33&&data[32]=='\n')) { r_log("pairing length invalid",n); return SCE_KERNEL_START_FAILED; }
    for(unsigned i=0;i<32;i++) if(!((data[i]>='0'&&data[i]<='9')||(data[i]>='a'&&data[i]<='f'))) { r_log("pairing format invalid",-1); return SCE_KERNEL_START_FAILED; }
    R_MEMCPY(pairing,data,32); pairing[32]=0;
    __atomic_store_n(&running,1,__ATOMIC_RELEASE);
    thread=sceKernelCreateThread("vita-resident",worker,0x40,64*1024,0,0,0);
    if(thread<0) { r_log("thread create failed",thread); return SCE_KERNEL_START_FAILED; }
    int result=sceKernelStartThread(thread,0,0);
    if(result<0) { r_log("thread start failed",result); sceKernelDeleteThread(thread); thread=-1; return SCE_KERNEL_START_FAILED; }
    r_log("module start 0.1.2",0); return SCE_KERNEL_START_SUCCESS;
}
int module_stop(SceSize args,const void *arg) {
    (void)args; (void)arg; __atomic_store_n(&running,0,__ATOMIC_RELEASE);
    if(thread>=0) { SceUInt timeout=5000000; int result=sceKernelWaitThreadEnd(thread,0,&timeout); if(result<0) { r_log("worker retained after join timeout",result); return SCE_KERNEL_STOP_CANCEL; } sceKernelDeleteThread(thread); thread=-1; }
    if(network_owned) { r_log("network pool retained until shell exits",0); return SCE_KERNEL_STOP_CANCEL; }
    return SCE_KERNEL_STOP_SUCCESS;
}
