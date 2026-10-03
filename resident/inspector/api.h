#ifndef VITA_INSPECTOR_API_H
#define VITA_INSPECTOR_API_H
#include <stdint.h>
#include <string.h>
#define VI_ABI 1
#define VI_MAGIC 0x31444956u
#define VI_ARGS_MAGIC 0x31414956u
#define VI_VERSION "01.03"
#define VI_SESSION_PATH "ux0:data/vita-control-inspector/kernel-session.lock"
#define VI_E_ARGUMENT ((int32_t)UINT32_C(0x80020005))
#define VI_E_DENIED ((int32_t)UINT32_C(0x80020008))
typedef struct {
    uint32_t magic, abi, size, reserved;
    int32_t caller_before, caller_after, shell_pid, guard_allowed;
    uint64_t tick_us;
    char build_id[65];
    unsigned char padding[7];
} VIInfo;
typedef struct { uint32_t magic, mode; char run[33]; unsigned char padding[3]; } VIArgs;
_Static_assert(sizeof(VIInfo)==112, "Fixed metadata ABI");
_Static_assert(sizeof(VIArgs)==44, "Fixed probe arguments");
static inline int viValidArgs(unsigned size, const void *arg) {
    if(size!=sizeof(VIArgs) || !arg) return 0;
    const VIArgs *args=arg;
    if(args->magic!=VI_ARGS_MAGIC || (args->mode!=1 && args->mode!=2) || args->run[32] ||
        args->padding[0] || args->padding[1] || args->padding[2]) return 0;
    for(unsigned i=0;i<32;i++)
        if(!((args->run[i]>='0' && args->run[i]<='9') || (args->run[i]>='a' && args->run[i]<='f'))) return 0;
    return 1;
}
static inline int viEntryComplete(const char *entry,const char *build,const char *run) {
    const char *identity=strstr(entry,"\nbuild_id=");
    const char *nonce=strstr(entry,"\nrun_nonce=");
    return identity && nonce && !strncmp(identity+10,build,64) && identity[74]=='\n' &&
        !strncmp(nonce+11,run,32) && nonce[43]=='\n' &&
        strstr(entry,"\nstage=diagnostic finished result=0x00000000\n");
}
int viVersion(void);
int viInfo(VIInfo *out, unsigned size);
int viBuildId(char *out, unsigned size);
int viShellBuildId(char *out, unsigned size);
#endif
