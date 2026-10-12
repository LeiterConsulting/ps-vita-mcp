#ifndef VITA_LAUNCH_BROKER_TEST_NATIVE_PLATFORM_H
#define VITA_LAUNCH_BROKER_TEST_NATIVE_PLATFORM_H
#include <stdint.h>
typedef int32_t SceInt32;
typedef int32_t SceUID;
int sceAppMgrGetRunningAppIdListForShell(SceInt32 *apps,int capacity);
SceUID sceAppMgrGetProcessIdByAppIdForShell(SceInt32 app);
int sceAppMgrGetNameById(SceUID pid,char *title);
#endif
