#ifndef RC_TEST_BOOTSTRAP_PLATFORM_H
#define RC_TEST_BOOTSTRAP_PLATFORM_H
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef unsigned SceSize;
#define SCE_KERNEL_START_SUCCESS 0
#define SCE_KERNEL_STOP_SUCCESS 0
#define SCE_O_WRONLY 2
#define SCE_O_CREAT 0x200
#define SCE_O_EXCL 0x800
#define SCE_S_IRSYS 4
#define SCE_S_IWSYS 2
#define sceClibSnprintf snprintf
#define sceClibStrcmp strcmp
int sceIoOpen(const char *path,int flags,int mode);
int sceKernelGetProcessId(void);
int sceIoWrite(int fd,const void *data,unsigned size);
int sceIoClose(int fd);
int sceIoRename(const char *old_path,const char *new_path);
#endif
