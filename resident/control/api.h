#ifndef VITA_CONTROL_API_H
#define VITA_CONTROL_API_H
#include <stdint.h>
#define RC_ABI 1
#define RC_INPUT_MAGIC 0x31495256u
#define RC_READ_MAGIC 0x31425256u
#define RC_FRAME_MAGIC 0x31465256u
#define RC_BOOT_MAGIC 0x314d4356u
#define RC_BOOT_ARGS_MAGIC 0x31534356u
#define RC_BOOT_ROOT "ux0:data/vita-control"
#define RC_BOOT_GUARD RC_BOOT_ROOT "/control-session.lock"
typedef struct {
    uint32_t magic,abi,size,ready;
    int32_t caller_before,caller_after,shell_pid,guard_allowed;
    uint64_t tick_us;
    char build_id[65];
    unsigned char padding[7];
} RBootstrapInfo;
typedef struct { uint32_t magic,mode; char run[33]; unsigned char padding[3]; } RBootstrapArgs;
_Static_assert(sizeof(RBootstrapInfo)==112,"Fixed bootstrap metadata ABI");
_Static_assert(sizeof(RBootstrapArgs)==44,"Fixed starter session guard");
static inline int rcValidBootArgs(unsigned size,const void *arg) {
    if(size!=sizeof(RBootstrapArgs) || !arg) return 0;
    const RBootstrapArgs *args=arg;
    if(args->magic!=RC_BOOT_ARGS_MAGIC || args->mode!=1 || args->run[32] || args->padding[0] || args->padding[1] || args->padding[2]) return 0;
    for(unsigned i=0;i<32;i++) if(!((args->run[i]>='0' && args->run[i]<='9') || (args->run[i]>='a' && args->run[i]<='f'))) return 0;
    return 1;
}
int vitaControlBootstrapInfo(RBootstrapInfo *out,unsigned size);
/* Full-state replacement. One synthetic point on each panel in the first ABI. */
typedef struct {
    uint32_t magic,abi,ttl_ms,buttons,flags;
    uint32_t lx,ly,rx,ry,fx,fy,bx,by;
    int32_t target_pid;
} RInput;
typedef struct { RInput input; uint64_t expires_ms; uint32_t active,releases; } RLease;
typedef struct { uint32_t magic,abi; uint64_t sample_ms; RLease lease; int32_t sample_result; uint32_t buttons,lx,ly,rx,ry; } RReadback;
typedef struct {
    uint32_t magic,abi,sequence,width,height,bytes;
    int32_t pid;
    uint32_t vblank,source_width,source_height,flags,reserved;
    uint64_t started_us,ended_us;
} RFrame;
int vitaControlVersion(void);
int vitaControlBuildId(char *out,unsigned size);
int vitaControlInput(const RInput *input,unsigned size);
int vitaControlRelease(void);
int vitaControlReadback(RReadback *out,unsigned size);
int vitaControlCapture(void *pixels,unsigned capacity,RFrame *out,unsigned scale);
#endif
