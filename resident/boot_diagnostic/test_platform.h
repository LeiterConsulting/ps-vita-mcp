#ifndef VITA_BOOT_DIAGNOSTIC_TEST_PLATFORM_H
#define VITA_BOOT_DIAGNOSTIC_TEST_PLATFORM_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned SceSize;
typedef unsigned SceUInt;
typedef int SceUID;
typedef int32_t SceInt32;
typedef struct { int64_t st_size;unsigned st_mode; } SceIoStat;
#define SCE_KERNEL_START_SUCCESS 0
#define SCE_KERNEL_START_FAILED 1
#define SCE_KERNEL_STOP_CANCEL 1
#define SCE_O_RDONLY 1
#define SCE_O_WRONLY 2
#define SCE_O_APPEND 0x100
#define SCE_O_CREAT 0x200
#define SCE_O_EXCL 0x800
#define SCE_S_IRSYS 4
#define SCE_S_IWSYS 2
#define SCE_S_ISREG(mode) (((mode)&0xf000)==0x8000)
#define sceClibSnprintf snprintf
#define sceClibStrcmp strcmp
uint64_t sceKernelGetSystemTimeWide(void);
int sceKernelGetProcessId(void);
int sceKernelGetThreadId(void);
int sceKernelDelayThread(unsigned micros);
int sceIoGetstat(const char *path,SceIoStat *out);
int sceIoOpen(const char *path,int flags,int mode);
int sceIoRead(int fd,void *out,unsigned size);
int sceIoWrite(int fd,const void *bytes,unsigned size);
int sceIoClose(int fd);
int sceIoRename(const char *old_path,const char *new_path);
int sceIoSyncByFd(int fd,int flags);
int sceIoSync(const char *device,int flags);
int sceAppMgrGetRunningAppIdListForShell(int *apps,int capacity);
int sceAppMgrGetProcessIdByAppIdForShell(int app);
int sceAppMgrGetNameById(int pid,char *name);
int sceKernelCreateMutex(const char *name,int attrs,int count,void *options);
int sceKernelDeleteMutex(int mutex);
int sceKernelCreateThread(const char *name,int (*entry)(unsigned,void *),int priority,unsigned stack,int flags,int affinity,void *options);
int sceKernelStartThread(int thread,unsigned size,void *arg);
int sceKernelWaitThreadEnd(int thread,int *status,SceUInt *timeout);
int sceKernelDeleteThread(int thread);
#endif
