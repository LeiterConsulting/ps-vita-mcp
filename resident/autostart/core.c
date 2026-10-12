#include "autostart.h"
#include "../platform.h"

const char *ao_state_name(AOState state) {
    static const char *const names[] = {
        "disabled", "waiting for LiveArea", "cancelled", "readiness deadline",
        "guard blocked", "one-shot claim failed", "module files rejected",
        "kernel submission failed", "probe submission failed",
        "Shell metadata rejected", "temporary probe release failed",
        "service submission failed", "modules submitted; network unverified"
    };
    return (unsigned)state < sizeof(names)/sizeof(names[0]) ? names[state] : "invalid state";
}

int ao_valid_metadata(const AOProbe *probe, int own_pid, const char *build_id) {
    const RBootstrapInfo *info = &probe->info;
    for(unsigned i=0;i<sizeof(info->padding);i++) if(info->padding[i]) return 0;
    return probe->module_id >= 0 && probe->start_result == 0 &&
        probe->metadata_result == 0 && own_pid > 0 &&
        info->magic == RC_BOOT_MAGIC && info->abi == RC_ABI &&
        info->size == sizeof(*info) && info->ready == 1 &&
        info->caller_before == own_pid && info->caller_after == own_pid &&
        info->shell_pid == own_pid && info->guard_allowed == 1 &&
        info->build_id[64] == 0 && !R_STRCMP(info->build_id, build_id);
}

static AOResult finish(const AOPlatform *p, void *ctx, AOResult result,
                       AOState state, int code) {
    result.state = state;
    p->event(ctx, state, code);
    return result;
}

AOResult ao_run(const AOPlatform *p, void *ctx, int own_pid, const char *build_id) {
    AOResult out = {.state=AO_DISABLED, .kernel_id=-1, .probe_id=-1, .service_id=-1};
    if(own_pid<=0) return finish(p,ctx,out,AO_GUARD_BLOCKED,-1);
    int result = p->armed(ctx);
    if(result != 1) return finish(p,ctx,out,AO_DISABLED,result);
    result = p->guards_clear(ctx);
    if(result != 1) return finish(p,ctx,out,AO_GUARD_BLOCKED,result);
    uint64_t started = p->now_ms(ctx), previous = started;
    unsigned stable = 0;
    p->event(ctx,AO_WAITING,0);
    for(;;) {
        if(!p->running(ctx)) return finish(p,ctx,out,AO_CANCELLED,0);
        uint64_t now = p->now_ms(ctx);
        if(now < previous || now-started >= AO_DEADLINE_MS)
            return finish(p,ctx,out,AO_READINESS_TIMEOUT,-1);
        previous = now;
        if(now >= AO_MIN_UPTIME_MS && p->ready(ctx) == 1) stable++;
        else stable = 0;
        if(stable >= AO_STABLE_SAMPLES) break;
        p->delay_ms(ctx,AO_SAMPLE_MS);
    }
    if(!p->running(ctx)) return finish(p,ctx,out,AO_CANCELLED,0);
    result = p->guards_clear(ctx);
    if(result != 1) return finish(p,ctx,out,AO_GUARD_BLOCKED,result);
    result = p->claim(ctx);
    if(result != 0) return finish(p,ctx,out,AO_CLAIM_FAILED,result);
    out.claimed = 1;
    result = p->verify_files(ctx);
    if(result != 0) return finish(p,ctx,out,AO_FILES_REJECTED,result);
    if(!p->running(ctx)) return finish(p,ctx,out,AO_CANCELLED,0);
    out.kernel_id = p->load_kernel(ctx);
    if(out.kernel_id < 0) return finish(p,ctx,out,AO_KERNEL_FAILED,out.kernel_id);
    if(!p->running(ctx)) return finish(p,ctx,out,AO_CANCELLED,0);
    AOProbe probe = p->load_probe(ctx);
    out.probe_id = probe.module_id;
    if(probe.module_id < 0) return finish(p,ctx,out,AO_PROBE_FAILED,probe.module_id);
    int valid = ao_valid_metadata(&probe,own_pid,build_id);
    result = p->release_probe(ctx,probe.module_id);
    if(result != 0) return finish(p,ctx,out,AO_PROBE_RELEASE_FAILED,result);
    if(!valid) return finish(p,ctx,out,AO_METADATA_REJECTED,probe.metadata_result);
    if(!p->running(ctx)) return finish(p,ctx,out,AO_CANCELLED,0);
    int start_result = -1;
    out.service_id = p->load_service(ctx,&start_result);
    if(out.service_id < 0 || start_result != 0)
        return finish(p,ctx,out,AO_SERVICE_FAILED,out.service_id < 0 ? out.service_id : start_result);
    /* Submission is deliberately separate from external network acceptance. */
    return finish(p,ctx,out,AO_MODULES_SUBMITTED,0);
}
