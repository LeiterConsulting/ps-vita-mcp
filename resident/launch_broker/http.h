#ifndef VITA_LAUNCH_BROKER_HTTP_H
#define VITA_LAUNCH_BROKER_HTTP_H
#include "launch_broker.h"
#include <stddef.h>

#define LB_HTTP_BODY_MAX 2048u
#define LB_HTTP_REPLY_MIN 2048u

typedef struct {
    char attempt[33];
    int armed;
} LBDeferred;

/* Serialized, allocation-free JSON route dispatch; never calls the launch
 * adapter or lb_dispatch_after_response. admin must be exactly 1, supplied by
 * the authenticated transport. Phone credentials may not read this namespace.
 * GET status/receipt reject bodies. POST accepts exactly seven canonical fields.
 * No escaped JSON strings, duplicate/unknown fields or non-integer numbers.
 *
 * reply receives bounded JSON and the return value is its HTTP status. Capacity
 * must be >=LB_HTTP_REPLY_MIN before an offer can be durably claimed. deferred
 * is cleared on entry and armed only for a fully encoded accepted 202 reply.
 * The owning service must finish sending that reply, return from its client
 * handler AND CLOSE THE SOCKET before invoking lb_dispatch_after_response with
 * the exact attempt and response_complete (bytes sent, not client acknowledgement).
 * Dispatch is never retried after a lost/invalid response or service restart. */
int lb_http_dispatch(LBCore *core,int admin,const char *method,const char *path,
                     const void *body,size_t size,char *reply,size_t capacity,
                     LBDeferred *deferred);
#endif
