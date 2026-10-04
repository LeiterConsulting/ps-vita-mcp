#include "lease.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    RInput input={RC_INPUT_MAGIC,RC_ABI,100,0x4000,5,128,128,128,128,500,600,0,0,77}; RLease lease={0};
    assert(rlease_valid(&input)); rlease_apply(&lease,&input,1000);
    assert(!rlease_expired(&lease,1099,77)); assert(rlease_expired(&lease,1100,77)); assert(rlease_expired(&lease,1001,88));
    rlease_clear(&lease,1100,RC_RELEASE_EXPIRED); assert(!lease.active&&!lease.input.buttons&&!lease.input.flags&&lease.releases==1); rlease_clear(&lease,1100,RC_RELEASE_EXPIRED); assert(lease.releases==1);
    assert(lease.release_reason==RC_RELEASE_EXPIRED&&lease.released_ms==1100);
    input.ttl_ms=1001; assert(!rlease_valid(&input)); input.ttl_ms=15; assert(!rlease_valid(&input)); input.ttl_ms=16;
    input.buttons=0x10000; assert(!rlease_valid(&input)); input.buttons=0; input.flags=16; assert(!rlease_valid(&input)); input.flags=0;
    input.lx=256; assert(!rlease_valid(&input)); input.lx=0; input.fx=1920; assert(!rlease_valid(&input)); input.fx=1919;
    input.by=1088; assert(!rlease_valid(&input)); input.by=1087; input.target_pid=-1; assert(!rlease_valid(&input));
    input.target_pid=77; assert(rlease_valid(&input)); rlease_apply(&lease,&input,5000); assert(lease.expires_ms==5016);
    assert(rlease_reason(&lease,5001,88)==RC_RELEASE_FOCUS);
    rlease_clear(&lease,5001,RC_RELEASE_FOCUS); assert(lease.release_reason==RC_RELEASE_FOCUS&&lease.released_ms==5001);
    rlease_clear(&lease,6000,RC_RELEASE_MANUAL); assert(lease.release_reason==RC_RELEASE_FOCUS);
    rlease_apply(&lease,&input,7000); rlease_apply(&lease,&input,7001); assert(lease.release_reason==RC_RELEASE_REPLACED&&lease.released_ms==7001);
    assert(rlease_reason(&lease,8000,88)==RC_RELEASE_EXPIRED); input.abi=1; assert(!rlease_valid(&input));
    puts("Lease expiry, focus cancellation, repeated release, coordinate/TTL/button bounds: PASS"); return 0;
}
