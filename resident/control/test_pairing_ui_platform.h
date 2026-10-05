#ifndef VITA_TEST_PAIRING_UI_PLATFORM_H
#define VITA_TEST_PAIRING_UI_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
typedef int SceUID;
typedef struct {int unused;} vita2d_pgf;
typedef struct {unsigned short year,month,day,hour,minute,second;} SceDateTime;
typedef struct {void *memory;size_t size;int flags;} SceNetInitParam;
#define SCE_CTRL_CROSS 16384u
#define SCE_CTRL_CIRCLE 8192u
#define SCE_CTRL_SQUARE 32768u
#define SCE_CTRL_TRIANGLE 4096u
#define SCE_CTRL_DOWN 64u
#define SCE_CTRL_UP 16u
#define SCE_SYSMODULE_NET 1
#define SCE_O_RDONLY 1
#define SCE_O_WRONLY 2
#define SCE_O_CREAT 4
#define SCE_O_APPEND 8
int sceKernelLockMutex(int,int,void *);
int sceKernelUnlockMutex(int,int);
uint64_t sceKernelGetSystemTimeWide(void);
int sceKernelGetRandomNumber(void *,unsigned);
int sceKernelDelayThread(unsigned);
int sceRtcSetTime64_t(SceDateTime *,uint64_t);
int sceIoOpen(const char *,int,int);
int sceIoRead(int,void *,unsigned);
int sceIoWrite(int,const void *,unsigned);
int sceIoClose(int);
int sceKernelCreateMutex(const char *,int,int,void *);
int sceKernelCreateThread(const char *,int (*)(unsigned,void *),int,unsigned,int,int,void *);
int sceKernelStartThread(int,unsigned,void *);
int sceKernelDeleteThread(int);
int sceKernelWaitThreadEnd(int,void *,void *);
int sceKernelDeleteMutex(int);
int sceSysmoduleIsLoaded(int);
int sceSysmoduleLoadModule(int);
int sceNetInit(SceNetInitParam *);
int sceNetTerm(void);
void vita2d_pgf_draw_text(vita2d_pgf *,int,int,unsigned,float,const char *);
#endif
