#ifndef VITA_PAIRING_CLIENT_H
#define VITA_PAIRING_CLIENT_H
#include "pairing.h"
typedef struct {
    uint64_t (*mono)(void);
    void (*delay)(unsigned ms);
    int (*connect)(unsigned port); /* loopback only; nonblocking, bounded */
    int (*send)(int fd,const void *data,size_t bytes);
    int (*recv)(int fd,void *data,size_t bytes);
    void (*close)(int fd);
} PCIO;
/* No retries: an interrupted POST can have committed. 0 means uncertain/unavailable. */
int pc_call(const PCIO *io,unsigned port,const char admin[33],const char *path,
            const char *body,char out[PR_JSON_MAX]);
int pc_authorized(const PCIO *io,unsigned port,const char admin[33],const char token[33],int renew);
int pc_capture_allowed(const PCIO *io,unsigned port,const char admin[33]);
const PCIO *pc_platform_io(void);
#endif
