#ifndef VITA_CONTROL_API_H
#define VITA_CONTROL_API_H
#include <stdint.h>
#define RC_ABI 2
#define RC_VERSION "0.3.4"
enum { RC_RELEASE_NONE, RC_RELEASE_EXPIRED, RC_RELEASE_FOCUS, RC_RELEASE_MANUAL, RC_RELEASE_REPLACED, RC_RELEASE_STOP };
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
typedef struct { RInput input; uint64_t expires_ms; uint32_t active,releases; uint32_t release_reason,reserved; uint64_t released_ms; } RLease;
typedef struct { uint32_t magic,abi; uint64_t sample_ms; RLease lease; int32_t sample_result; uint32_t buttons,lx,ly,rx,ry; } RReadback;
_Static_assert(sizeof(RLease)==88,"Fixed lease ABI");
_Static_assert(sizeof(RReadback)==128,"Fixed readback ABI");
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
int vitaControlBrightness(int value); /* -1 reads; 21..65536 sets; zero/off forbidden. */
typedef struct {
    int32_t reader_pid,last_reader_pid;
    uint32_t native_contacts,reads,advances,hook_reads;
    uint64_t source_ticks,received_ms,changed_ms;
} RTouchPanel;
typedef struct {
    uint32_t magic,abi,panels,reserved; int32_t foreground_pid; uint32_t padding; uint64_t sampled_ms;
    RTouchPanel panel[2];
} RTouchActivity;
_Static_assert(sizeof(RTouchPanel)==48,"Fixed touch diagnostic panel");
_Static_assert(sizeof(RTouchActivity)==128,"Fixed touch activity syscall");
#define RC_TOUCH_MAGIC 0x31545256u
int vitaControlTouchActivity(RTouchActivity *out,unsigned size);
#endif
