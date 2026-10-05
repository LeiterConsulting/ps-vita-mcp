#include "lease.h"
int rlease_valid(const RInput *i) {
    /* PS, power, volume and service-only buttons are outside this first ABI. */
    const uint32_t allowed=0x0000f3f9;
    return i->magic==RC_INPUT_MAGIC&&i->abi==RC_ABI&&i->ttl_ms>=16&&i->ttl_ms<=1000&&
           !(i->buttons&~allowed)&&!(i->flags&~15u)&&i->lx<=255&&i->ly<=255&&i->rx<=255&&i->ry<=255&&
           i->fx<=1919&&i->fy<=1087&&i->bx<=1919&&i->by<=1087&&i->target_pid>0;
}
void rlease_apply(RLease *lease,const RInput *input,uint64_t now_ms) { rlease_clear(lease,now_ms,RC_RELEASE_REPLACED); lease->input=*input; lease->expires_ms=now_ms+input->ttl_ms; lease->active=1; }
void rlease_clear(RLease *lease,uint64_t now_ms,uint32_t reason) {
    if(lease->active) { lease->releases++; lease->release_reason=reason; lease->released_ms=now_ms; }
    lease->active=0; lease->expires_ms=0;
    lease->input=(RInput){0};
}
uint32_t rlease_reason(const RLease *lease,uint64_t now_ms,int32_t pid) {
    if(!lease->active) return RC_RELEASE_NONE;
    if(now_ms>=lease->expires_ms) return RC_RELEASE_EXPIRED;
    return pid!=lease->input.target_pid?RC_RELEASE_FOCUS:RC_RELEASE_NONE;
}
int rlease_expired(const RLease *lease,uint64_t now_ms,int32_t pid) { return rlease_reason(lease,now_ms,pid)!=RC_RELEASE_NONE; }
