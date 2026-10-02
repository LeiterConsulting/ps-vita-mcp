/* Test-only POSIX replacements for Vita kernel, socket and display APIs.
 * Production builds never include this file. */
#pragma once
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <fcntl.h>
#include <time.h>
#include <unistd.h>
typedef int SceUID;
typedef size_t SceSize;
typedef unsigned SceUInt;
typedef struct { unsigned s_addr; } SceNetInAddr;
typedef struct { unsigned char sin_len,sin_family; unsigned short sin_port; SceNetInAddr sin_addr; unsigned short sin_vport; char sin_zero[6]; } SceNetSockaddrIn;
typedef SceNetSockaddrIn SceNetSockaddr;
typedef struct { void *memory; int size,flags; } SceNetInitParam;
typedef union { char ip_address[16]; } SceNetCtlInfo;
typedef struct { unsigned size; void *base; unsigned pitch,pixelformat,width,height; } SceDisplayFrameBuf;
#define SCE_NET_EAGAIN EAGAIN
#define SCE_NET_EWOULDBLOCK EWOULDBLOCK
#define SCE_NET_SOL_SOCKET SOL_SOCKET
#define SCE_NET_SO_NBIO 0x1100
#define SCE_NET_SO_REUSEADDR SO_REUSEADDR
#define SCE_NET_AF_INET AF_INET
#define SCE_NET_SOCK_STREAM SOCK_STREAM
#define SCE_NET_INADDR_ANY INADDR_ANY
#define SCE_SYSMODULE_NET 1
#define SCE_NETCTL_STATE_CONNECTED 3
#define SCE_NETCTL_INFO_GET_IP_ADDRESS 15
#define SCE_DISPLAY_SETBUF_IMMEDIATE 0
#define SCE_DISPLAY_PIXELFORMAT_A8B8G8R8 0
static pthread_mutex_t shim_mutex;
static SceDisplayFrameBuf shim_fb;
static unsigned shim_gpu_waits,shim_queue_waits;
static uint64_t sceKernelGetProcessTimeWide(void) { struct timespec t; assert(!clock_gettime(CLOCK_MONOTONIC,&t)); return (uint64_t)t.tv_sec*1000000+(uint64_t)t.tv_nsec/1000; }
static int sceKernelCreateMutex(const char *name,int attr,int count,void *option) { assert(!pthread_mutex_init(&shim_mutex,NULL)); return 1; }
static int sceKernelLockMutex(SceUID id,int count,void *timeout) { assert(id==1); return pthread_mutex_lock(&shim_mutex); }
static int sceKernelUnlockMutex(SceUID id,int count) { assert(id==1); return pthread_mutex_unlock(&shim_mutex); }
static int sceKernelDeleteMutex(SceUID id) { assert(id==1); return pthread_mutex_destroy(&shim_mutex); }
static int sceKernelCreateThread(const char *name,int (*entry)(SceSize,void*),int priority,unsigned stack,int attr,int affinity,void *option) { return -1; }
static int sceKernelStartThread(SceUID id,SceSize size,void *args) { return -1; }
static int sceKernelWaitThreadEnd(SceUID id,int *status,SceUInt *timeout) { return 0; }
static int sceKernelDeleteThread(SceUID id) { return 0; }
static int sceKernelDelayThread(unsigned us) { return usleep(us); }
static int *sceNetErrnoLoc(void) { return &errno; }
static int sceNetSetsockopt(int s,int level,int option,const void *value,unsigned length) {
    if(option==SCE_NET_SO_NBIO) return fcntl(s,F_SETFL,fcntl(s,F_GETFL)|O_NONBLOCK);
    return setsockopt(s,level,option,value,length);
}
static int sceNetSend(int s,const void *data,size_t length,int flags) { return (int)send(s,data,length,flags|MSG_NOSIGNAL); }
static int sceNetRecv(int s,void *data,size_t length,int flags) { return (int)recv(s,data,length,flags); }
static int sceNetSocket(const char *name,int domain,int type,int protocol) { return socket(domain,type,protocol); }
static int sceNetBind(int s,SceNetSockaddr *address,unsigned length) { return -1; }
static int sceNetListen(int s,int backlog) { return listen(s,backlog); }
static int sceNetAccept(int s,SceNetSockaddr *address,unsigned *length) { return accept(s,NULL,NULL); }
static int sceNetSocketClose(int s) { return close(s); }
static unsigned short sceNetHtons(unsigned short value) { return htons(value); }
static unsigned sceNetHtonl(unsigned value) { return htonl(value); }
static int sceNetInit(SceNetInitParam *parameter) { return 0; }
static int sceNetTerm(void) { return 0; }
static int sceNetCtlInit(void) { return 0; }
static int sceNetCtlTerm(void) { return 0; }
static int sceNetCtlInetGetState(int *state) { *state=0; return 0; }
static int sceNetCtlInetGetInfo(int type,SceNetCtlInfo *info) { return -1; }
static int sceSysmoduleLoadModule(int module) { return 0; }
static int sceSysmoduleUnloadModule(int module) { return 0; }
static void vita2d_wait_rendering_done(void) { shim_gpu_waits++; }
static int sceGxmDisplayQueueFinish(void) { shim_queue_waits++; return 0; }
static int sceDisplayGetFrameBuf(SceDisplayFrameBuf *out,int sync) { *out=shim_fb; return shim_fb.base?0:-1; }
