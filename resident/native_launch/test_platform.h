#ifndef VITA_NATIVE_LAUNCH_TEST_PLATFORM_H
#define VITA_NATIVE_LAUNCH_TEST_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
typedef int32_t SceInt32;
typedef int32_t SceUID;
typedef size_t SceSize;
typedef struct {
    uint32_t systemEventNum,appEventNum;
    int32_t isSystemUiOverlaid;
    unsigned char reserved[116];
} SceAppMgrAppState;
int sceAppMgrGetRunningAppIdListForShell(SceInt32 *apps,int count);
SceUID sceAppMgrGetProcessIdByAppIdForShell(SceInt32 app);
int sceAppMgrGetNameById(SceUID pid,char *title);
int _sceAppMgrGetAppState(SceAppMgrAppState *state,SceSize size,uint32_t version);
int sceAppMgrLaunchAppByUri(int flags,const char *uri);
#endif
