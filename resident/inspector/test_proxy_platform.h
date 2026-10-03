#ifndef VI_TEST_PROXY_PLATFORM_H
#define VI_TEST_PROXY_PLATFORM_H
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef unsigned SceSize;
#define SCE_KERNEL_START_SUCCESS 0
#define SCE_KERNEL_STOP_SUCCESS 0
#define SCE_O_WRONLY 2
#define SCE_O_RDONLY 1
#define SCE_O_CREAT 0x200
#define SCE_O_TRUNC 0x400
#define SCE_O_APPEND 0x100
#define SCE_O_EXCL 0x800
#define SCE_S_IRSYS 4
#define SCE_S_IWSYS 2
#define sceClibSnprintf snprintf
#define sceClibStrcmp strcmp
int sceKernelGetProcessId(void);
int sceIoOpen(const char *path,int flags,int mode);
int sceIoWrite(int fd,const void *data,unsigned size);
int sceIoRead(int fd,void *data,unsigned size);
int sceIoClose(int fd);
int sceIoRename(const char *old_path,const char *new_path);
#endif
