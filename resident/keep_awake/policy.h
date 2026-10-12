#ifndef VITA_RESIDENT_KEEP_AWAKE_POLICY_H
#define VITA_RESIDENT_KEEP_AWAKE_POLICY_H
#include <stddef.h>
#include <stdint.h>
#define RKA_PORT 17869
#define RKA_MAGIC 0x31414b52u
#define RKA_PROTOCOL 1u
#define RKA_WIRE_BYTES 128u
#define RKA_TTL_MIN 5000u
#define RKA_TTL_MAX 30000u
#define RKA_SESSION_MIN 30000u
#define RKA_SESSION_MAX 1800000u
#define RKA_GAP_MAX 5000u
typedef struct {
    uint32_t revision,ttl_ms,max_duration_ms;
    char instance_id[33],lease_id[33],job_id[33];
} RKARequest;
typedef struct {
    char instance_id[33],lease_id[33],job_id[33];
    uint64_t last_clock_ms,expires_ms,session_expires_ms,last_tick_ms,tick_count;
    uint32_t revision;
    int clock_valid,network_ready,active,tick_result,tick_pending;
    const char *reason;
} RKAState;
void rka_policy_init(RKAState *state,const char instance_id[33]);
int rka_decode(RKARequest *request,const unsigned char *wire,size_t size);
/* Step before admitting requests and at least every 100 ms. Reads never renew. */
int rka_policy_step(RKAState *state,uint64_t now_ms,int network_ready);
/* 200 accepted; 400 invalid; 409 stale/wrong owner; 503 unsafe state. */
int rka_policy_apply(RKAState *state,const RKARequest *request,uint64_t now_ms);
void rka_policy_tick(RKAState *state,uint64_t now_ms,int result);
void rka_policy_end(RKAState *state,const char *reason);
#endif
