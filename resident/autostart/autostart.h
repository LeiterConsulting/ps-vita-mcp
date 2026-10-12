#ifndef VITA_AUTOSTART_H
#define VITA_AUTOSTART_H
#include "../control/api.h"
#include <stdint.h>

#define AO_ROOT "ux0:data/vita-autostart"
#define AO_MIN_UPTIME_MS 15000u
#define AO_DEADLINE_MS 120000u
#define AO_SAMPLE_MS 500u
#define AO_STABLE_SAMPLES 3u

typedef enum {
    AO_DISABLED, AO_WAITING, AO_CANCELLED, AO_READINESS_TIMEOUT,
    AO_GUARD_BLOCKED, AO_CLAIM_FAILED, AO_FILES_REJECTED, AO_KERNEL_FAILED,
    AO_PROBE_FAILED, AO_METADATA_REJECTED, AO_PROBE_RELEASE_FAILED,
    AO_SERVICE_FAILED, AO_MODULES_SUBMITTED
} AOState;

typedef struct {
    int module_id, start_result, metadata_result;
    RBootstrapInfo info;
} AOProbe;

typedef struct {
    uint64_t (*now_ms)(void *);
    int (*running)(void *);
    void (*delay_ms)(void *, unsigned);
    /* 1 = exactly armed, 0 = absent/disabled, negative = invalid/error. */
    int (*armed)(void *);
    int (*ready)(void *);
    /* Must recheck disable, prior in-flight and legacy guard immediately. */
    int (*guards_clear)(void *);
    /* Consume the opt-in atomically and retain a guard before native loading. */
    int (*claim)(void *);
    int (*verify_files)(void *);
    int (*load_kernel)(void *);
    AOProbe (*load_probe)(void *);
    int (*release_probe)(void *, int module_id);
    int (*load_service)(void *, int *start_result);
    void (*event)(void *, AOState, int);
} AOPlatform;

typedef struct {
    AOState state;
    int kernel_id, probe_id, service_id;
    int claimed, network_verified;
} AOResult;

const char *ao_state_name(AOState state);
int ao_valid_metadata(const AOProbe *probe, int own_pid, const char *build_id);
AOResult ao_run(const AOPlatform *platform, void *context, int own_pid,
                const char *build_id);
#endif
