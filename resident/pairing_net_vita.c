#include "pairing_client.h"
#include <psp2/kernel/threadmgr.h>
#include <psp2/net/net.h>
static uint64_t mono(void){return sceKernelGetSystemTimeWide()/1000;}
static void delay(unsigned ms){sceKernelDelayThread(ms*1000);}
static int again(void){int e=*sceNetErrnoLoc();return e==SCE_NET_EAGAIN||e==SCE_NET_EWOULDBLOCK;}
static int connect_local(unsigned port) {
    int fd=sceNetSocket("pairing-local",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0);if(fd<0)return -1;
    int on=1;if(sceNetSetsockopt(fd,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&on,sizeof(on))<0)goto fail;
    SceNetSockaddrIn a={0};a.sin_len=sizeof(a);a.sin_family=SCE_NET_AF_INET;a.sin_port=sceNetHtons(port);a.sin_addr.s_addr=sceNetHtonl(0x7f000001u);
    if(sceNetConnect(fd,(SceNetSockaddr *)&a,sizeof(a))==0)return fd;
    int e=*sceNetErrnoLoc();if(e!=SCE_NET_EINPROGRESS&&e!=SCE_NET_EALREADY&&e!=SCE_NET_EWOULDBLOCK)goto fail;
    uint64_t end=mono()+300;
    while(mono()<end){int error=0;unsigned size=sizeof(error);if(sceNetGetsockopt(fd,SCE_NET_SOL_SOCKET,SCE_NET_SO_ERROR,&error,&size)<0||error)goto fail;
        SceNetSockaddrIn peer={0};size=sizeof(peer);if(sceNetGetpeername(fd,(SceNetSockaddr *)&peer,&size)>=0)return fd;delay(5);}
fail:sceNetSocketClose(fd);return -1;
}
static int send_local(int fd,const void *data,size_t n){int r=sceNetSend(fd,data,n,0);return r<0&&again()?-2:r;}
static int recv_local(int fd,void *data,size_t n){int r=sceNetRecv(fd,data,n,0);return r<0&&again()?-2:r;}
static void close_local(int fd){sceNetSocketClose(fd);}
const PCIO *pc_platform_io(void){static const PCIO io={mono,delay,connect_local,send_local,recv_local,close_local};return &io;}
