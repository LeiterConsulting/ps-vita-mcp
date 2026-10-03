#include "lease.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    RInput input={RC_INPUT_MAGIC,RC_ABI,100,0x4000,5,128,128,128,128,500,600,0,0,77}; RLease lease={0};
    assert(rlease_valid(&input)); rlease_apply(&lease,&input,1000);
    assert(!rlease_expired(&lease,1099,77)); assert(rlease_expired(&lease,1100,77)); assert(rlease_expired(&lease,1001,88));
    rlease_clear(&lease); assert(!lease.active&&!lease.input.buttons&&!lease.input.flags&&lease.releases==1); rlease_clear(&lease); assert(lease.releases==1);
    input.ttl_ms=1001; assert(!rlease_valid(&input)); input.ttl_ms=15; assert(!rlease_valid(&input)); input.ttl_ms=16;
    input.buttons=0x10000; assert(!rlease_valid(&input)); input.buttons=0; input.flags=16; assert(!rlease_valid(&input)); input.flags=0;
    input.lx=256; assert(!rlease_valid(&input)); input.lx=0; input.fx=1920; assert(!rlease_valid(&input)); input.fx=1919;
    input.by=1088; assert(!rlease_valid(&input)); input.by=1087; input.target_pid=-1; assert(!rlease_valid(&input));
    input.target_pid=77; assert(rlease_valid(&input)); rlease_apply(&lease,&input,5000); assert(lease.expires_ms==5016);
    puts("Lease expiry, focus cancellation, repeated release, coordinate/TTL/button bounds: PASS"); return 0;
}
