#ifndef VITA_AUTOSTART_TEST_VITA_PLATFORM_H
#define VITA_AUTOSTART_TEST_VITA_PLATFORM_H
#include <stdio.h>
#include <string.h>
#include <stdint.h>
typedef unsigned SceSize;
typedef int SceUID;
typedef int32_t SceInt32;
typedef struct { int64_t st_size;unsigned st_mode; } SceIoStat;
typedef struct { unsigned size;int pid;unsigned args;const void *argp;int flags; } tai_module_args_t;
#define KERNEL_PID 0x10005
#define SCE_KERNEL_START_SUCCESS 0
#define SCE_KERNEL_START_FAILED 1
#define SCE_KERNEL_STOP_SUCCESS 0
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
#define AO_PROBE_SHA256 "ba9c736f19e7f60b7f6764adb0b7908c0a2b394e09b6c09863528c7f2bc86095"
uint64_t sceKernelGetSystemTimeWide(void);
int sceKernelGetProcessId(void);
int sceKernelDelayThread(unsigned micros);
int sceIoGetstat(const char *path,SceIoStat *out);
int sceIoOpen(const char *path,int flags,int mode);
int sceIoRead(int fd,void *out,unsigned size);
int sceIoWrite(int fd,const void *bytes,unsigned size);
int sceIoClose(int fd);
int sceIoRename(const char *old_path,const char *new_path);
int sceIoSyncByFd(int fd,int flags);
int sceIoSync(const char *device,int flags);
int sceIoMkdir(const char *path,int mode);
int sceAppMgrGetRunningAppIdListForShell(int *apps,int capacity);
int sceAppMgrGetProcessIdByAppIdForShell(int app);
int sceAppMgrGetNameById(int pid,char *name);
int taiLoadStartKernelModuleForUser(const char *path,tai_module_args_t *args);
int sceKernelLoadStartModule(const char *path,unsigned size,const void *args,int flags,void *options,int *status);
int sceKernelStopUnloadModule(int module,unsigned size,const void *args,int flags,void *options,int *status);
int sceKernelCreateThread(const char *name,int (*entry)(unsigned,void *),int priority,unsigned stack,int flags,int affinity,void *options);
int sceKernelStartThread(int thread,unsigned size,void *arg);
int sceKernelDeleteThread(int thread);
#endif
