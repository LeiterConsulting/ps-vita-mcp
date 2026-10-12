#ifndef VITA_NATIVE_LAUNCH_H
#define VITA_NATIVE_LAUNCH_H
#include <stddef.h>
#include <stdint.h>

#define NL_TITLE "VMCP00001"
#define NL_POLICY_REPLY_MAX 1024u
enum {
    NL_INVALID=-12000,NL_ENUMERATION=-12001,NL_CAPACITY=-12002,
    NL_UNRESOLVED=-12003,NL_APP_RUNNING=-12004,NL_STATE_UNAVAILABLE=-12005,
    NL_OVERLAY=-12006,NL_EVENTS=-12007,NL_STATE_INVALID=-12008,
    NL_NOT_RUNNING=-12009
};
typedef struct { int native_invoked;int result; } NLLaunchResult;

/* Conservative policy only. It does not attest displayed PID or absence of all
   protected UI. Both arguments are fixed policy: only NL_TITLE and 1 accepted.
   Read-only, no event consumption, input, lock changes or module loading. */
int nl_idle_policy(const char *target_title,int target_must_be_absent);
int nl_idle_ready(void);
int nl_policy_status(char *reply,size_t capacity);

/* Strict bounded native inventory. 0 absent/1 present/negative unavailable.
   All nonempty slots must resolve, including unrelated apps. */
int nl_target_absent(const char *title);
/* 0 found; negative absent/unavailable. Duplicate conflicting identities fail. */
int nl_inventory_pid(const char *title,int32_t *pid);

/* Fixed URI only; repeats conservative policy immediately before at most one
   SDK call. native_invoked distinguishes policy refusal from SDK submission.
   A nonnegative SDK result is submission, never runtime-readiness proof. */
NLLaunchResult nl_launch_owned_result(const char *title,const char *native_build_id);
int nl_launch_owned(const char *title,const char *native_build_id);
NLLaunchResult nl_launch_lab(const char *native_build_id);
#endif
