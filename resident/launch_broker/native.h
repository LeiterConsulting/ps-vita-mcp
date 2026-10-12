#ifndef VITA_LAUNCH_BROKER_NATIVE_H
#define VITA_LAUNCH_BROKER_NATIVE_H
#include <stddef.h>
#include <stdint.h>
#include "launch_broker.h"

#define LB_NATIVE_INVENTORY_CAPACITY 4096u
#define LB_NATIVE_LAUNCH_UNQUALIFIED (-1)

/* Call in the existing serialized Resident worker, never the loader thread.
   One 128-bit r_pair_random call per module lifetime; failures are retained.
   Returns 1 with 32 lowercase hex characters, or 0 with an empty output.
   An in-progress concurrent call fails without waiting or obtaining new RNG. */
int lb_native_instance(char out[33]);
uint64_t lb_native_now(void *ctx);

/* Unconditionally refuses: the pinned SDK inventory does not establish the
   displayed foreground or absence of protected UI. There is no launch import,
   opt-in file, PC assertion or boot path that enables this candidate.
   confirmed=0 means no confirmed native submission; retain the attempt fence
   if an integration mistakenly dispatches while its broker config is enabled. */
LBLaunchResult lb_native_launch(void *ctx);

/* Bounded read-only AppId -> PID -> title inventory. Returns JSON byte length,
   excluding NUL, or -1 with an empty reply if the local output is too small.
   An SDK enumeration failure is represented as available:false in the JSON.
   The list may be incomplete and its separate SDK reads are not atomic. Never
   use it as a foreground, protected-UI or launch-readiness attestation. */
int lb_native_inventory(char *reply,size_t capacity);
#endif
