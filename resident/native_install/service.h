#ifndef VITA_NATIVE_INSTALL_SERVICE_H
#define VITA_NATIVE_INSTALL_SERVICE_H
#include <stddef.h>
#include <stdint.h>

#define NI_FILE_COUNT 8u
#define NI_MAX_BODY 4096u
#define NI_MAX_FILE (8u*1024u*1024u)
#define NI_MAX_TOTAL (16u*1024u*1024u)
#define NI_TITLE "VMCP00001"
#define NI_PROJECT "lifecycle_lab"

/* Serialized in the existing delayed Resident worker; initialization and
   recovery never load a sysmodule, install, launch, or replay an operation. */
typedef struct { char attempt[33]; } NIDeferred;
typedef int (*NIRead)(void *ctx,void *out,size_t capacity);
void ni_init(void);
void ni_tick(void);
/* Return 0 for a different namespace; otherwise an HTTP status and JSON reply.
   Caller enforces JSON content-type, strict HTTP framing and NI_MAX_BODY. */
int ni_request(int admin,const char *method,const char *path,const void *body,
               size_t size,char *reply,size_t capacity,NIDeferred *deferred);
/* Call once only after response send AND socket close; complete is not proof
   the client received the response. Incomplete acceptance never dispatches. */
void ni_after_response(const NIDeferred *deferred,int complete);
/* PUT stream callback returns 1..capacity bytes, 0 EOF, negative error. The
   HTTP caller bounds native receive time and enforces exactly Content-Length.
   NI additionally enforces its operation clock deadline; no upload replay. */
int ni_upload(int admin,const char *method,const char *path,uint64_t length,
              const char *digest,NIRead read,void *ctx,char *reply,size_t capacity);
#endif
