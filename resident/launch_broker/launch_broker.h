#ifndef VITA_LAUNCH_BROKER_H
#define VITA_LAUNCH_BROKER_H
#include <stdint.h>

#define LB_TITLE "CHRS00003"
#define LB_FORMAT 1u
#define LB_MAX_TTL_MS 10000u
#define LB_MAX_AGE_MS 5000u

typedef enum { LB_ROLE_NONE=0,LB_ROLE_ADMIN=1,LB_ROLE_PHONE=2 } LBRole;
typedef enum {
    LB_EMPTY=0,LB_QUEUED,LB_DISPATCH_INTENT,LB_SUBMITTED,LB_NATIVE_REJECTED,
    LB_UNKNOWN,LB_OBSERVED,LB_EXPIRED,LB_CANCELLED
} LBState;
typedef enum {
    LB_REASON_NONE=0,LB_REASON_RESTART,LB_REASON_STORAGE,LB_REASON_RESPONSE,
    LB_REASON_DISABLED,LB_REASON_EXPIRY,LB_REASON_CLOCK,LB_REASON_NATIVE,
    LB_REASON_OBSERVATION
} LBReason;
typedef enum {
    LB_OK=0,LB_ACCEPTED=202,LB_BAD_REQUEST=400,LB_FORBIDDEN=403,
    LB_NOT_FOUND=404,LB_CONFLICT=409,LB_STALE=412,LB_UNAVAILABLE=503
} LBResult;
typedef struct {
    /* Role is supplied by the authenticated transport, never by request JSON. */
    LBRole role;
    char resident_build[65],instance[33];
} LBAuth;
typedef struct {
    LBAuth auth;
    char attempt[33],title[10],devloop_build[65];
    uint64_t issued_ms;
    uint32_t ttl_ms;
} LBRequest;
typedef struct {
    char title[10],version[6],build[65],run[33];
    int32_t pid;
    uint64_t frame,revision;
    int paused,faulted;
} LBObservation;
typedef struct {
    uint32_t format;
    LBState state;
    LBReason reason;
    char attempt[33],title[10],resident_build[65],instance[33],devloop_build[65];
    uint64_t issued_ms,expires_ms,accepted_ms,dispatch_ms;
    /* A durable dispatch fence, not a native success or a physical runtime claim. */
    unsigned dispatch_count;
    int native_confirmed;
    int32_t native_result;
    unsigned samples;
    LBObservation observation;
} LBReceipt;
typedef struct { int confirmed;int32_t result; } LBLaunchResult;
typedef struct {
    char resident_build[65],instance[33];
    int enabled;
} LBConfig;
typedef struct {
    uint64_t (*now_ms)(void *ctx);
    /* recover_last: 0 empty, 1 record, negative error. Never resumes dispatch. */
    int (*recover_last)(void *ctx,LBReceipt *out);
    /* claim: 0 durably created, 1 already claimed, negative unknown/failure.
       Exclusive attempt tombstones survive every restart and are never removed. */
    int (*claim)(void *ctx,const LBReceipt *receipt);
    /* save must atomically commit/sync this exact existing attempt; 0 success. */
    int (*save)(void *ctx,const LBReceipt *receipt);
    /* lookup: 0 record, 1 absent, negative error. No mutation or resubmission. */
    int (*lookup)(void *ctx,const char attempt[33],LBReceipt *out);
    /* No arbitrary title/URI/path parameter. This adapter launches LB_TITLE once.
       This call may block. There is no core timeout, cancellation or retry. */
    LBLaunchResult (*launch_fixed_title)(void *ctx);
} LBAdapter;
typedef struct {
    LBConfig config;
    LBAdapter adapter;
    void *ctx;
    LBReceipt current;
    uint64_t last_ms;
    int initialized,blocked,has_current;
} LBCore;

int lb_init(LBCore *core,const LBConfig *config,const LBAdapter *adapter,void *ctx);
int lb_offer(LBCore *core,const LBRequest *request,LBReceipt *out);
/* Internal serialized service hook: only after the offer's HTTP socket closed.
   response_complete means server bytes sent, not client acknowledgement. */
int lb_dispatch_after_response(LBCore *core,const char attempt[33],int response_complete,LBReceipt *out);
/* Historical lookup preserves the original receipt pins/state. An archived
   observed receipt is not current readiness; require current pins and runtime. */
int lb_get(LBCore *core,const LBAuth *auth,const char attempt[33],LBReceipt *out);
int lb_observe(LBCore *core,const LBAuth *auth,const char attempt[33],const LBObservation *observation,LBReceipt *out);
int lb_set_enabled(LBCore *core,int enabled);
/* Trusted native status sampling also participates in regression detection. */
int lb_status_clock(LBCore *core,uint64_t *now_ms);
int lb_receipt_valid(const LBReceipt *receipt);
const char *lb_state_name(LBState state);
#endif
