#ifndef VITA_LAUNCH_SERVICE_H
#define VITA_LAUNCH_SERVICE_H
#include <stddef.h>
#include "http.h"
#define R_VERSION "0.1.7"
int r_close_client(int socket); /* close result gates deferred dispatch */

/* One serialized Resident worker; initialization never dispatches a launch. */
void rlb_init(void);
int rlb_request(int admin,const char *method,const char *path,const void *body,
                size_t size,char *reply,size_t capacity,LBDeferred *deferred);
void rlb_after_response(const LBDeferred *deferred,int complete);
#endif
