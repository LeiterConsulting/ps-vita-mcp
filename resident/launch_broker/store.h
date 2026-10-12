#ifndef VITA_LAUNCH_BROKER_STORE_H
#define VITA_LAUNCH_BROKER_STORE_H
#include "launch_broker.h"

#define LB_STORE_ROOT "ux0:data/vita-resident/launch-v1"
#define LB_STORE_CAPACITY 128u
#define LB_STORE_WIRE_BYTES 543u

/* Serialized worker ownership only: not a multi-thread/process lock. All names
   are fixed, numbered, exclusive-created immutable records. No remove, rename,
   migration or pruning. Every failed/unknown write is retained and blocks this
   object. A fresh init also rejects torn records, gaps, invalid transitions,
   chain/build mismatches and the overflow sentinel. Without a directory-list
   wrapper, arbitrary unrelated filenames cannot be inventoried. Format 1 is
   supported only for the exact compiled R_BUILD_ID; old stores are preserved.
   Platform sync plus exact readback is an acceptance gate, not a claim about
   untested Vita filesystem power-loss durability. */
typedef struct {
    int initialized,blocked;
    unsigned count,attempt_count;
    LBReceipt latest;
    char digest[65];
    char attempts[LB_STORE_CAPACITY][33];
} LBStore;

/* Init may create only the fixed root. 0 ready, -1 retained/blocked. It never
   submits a launch or resumes a receipt. Full capacity refuses further writes.
   recover_last: 0 empty, 1 record, -1 error. claim: 0 committed, 1 duplicate or
   unresolved current intent, -1 error. save: 0 committed, -1 error. lookup:
   0 found, 1 absent, -1 error. Historical lookup retains its original pins. */
int lb_store_init(LBStore *store);
int lb_store_recover_last(void *ctx,LBReceipt *out);
int lb_store_claim(void *ctx,const LBReceipt *receipt);
int lb_store_save(void *ctx,const LBReceipt *receipt);
int lb_store_lookup(void *ctx,const char attempt[33],LBReceipt *out);
#endif
