#ifndef VITA_CONTROL_LEASE_H
#define VITA_CONTROL_LEASE_H
#include "api.h"
int rlease_valid(const RInput *input);
void rlease_apply(RLease *lease,const RInput *input,uint64_t now_ms);
void rlease_clear(RLease *lease,uint64_t now_ms,uint32_t reason);
uint32_t rlease_reason(const RLease *lease,uint64_t now_ms,int32_t foreground_pid);
int rlease_expired(const RLease *lease,uint64_t now_ms,int32_t foreground_pid);
#endif
