#ifndef VITA_RESIDENT_KEEP_AWAKE_PLATFORM_H
#define VITA_RESIDENT_KEEP_AWAKE_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
enum { RKA_STAGE_NONE,RKA_STAGE_SOCKET,RKA_STAGE_REUSE,RKA_STAGE_BIND,RKA_STAGE_LISTEN,RKA_STAGE_LISTENER_NBIO,RKA_STAGE_ACCEPT,RKA_STAGE_CLIENT_NBIO,RKA_STAGE_RECV,RKA_STAGE_SEND,RKA_STAGE_CLOSE };
typedef struct { int32_t result,error,stage,close_result,close_error; } RKASocketResult;
typedef struct { int32_t result,state; } RKANetworkResult;
uint64_t rkap_now(void);
int rkap_tick(void);
RKANetworkResult rkap_network(void);
int rkap_listen(RKASocketResult *result);
int rkap_accept(int socket,RKASocketResult *result);
int rkap_recv(int socket,void *data,size_t size,RKASocketResult *result);
int rkap_send(int socket,const void *data,size_t size,RKASocketResult *result);
int rkap_close(int socket,RKASocketResult *result);
int rkap_worker_start(void (*worker)(void));
int rkap_worker_join(void);
#ifndef __vita__
/* Host-only synthetic adapters, excluded from the Vita artifact. */
void rkap_host_config(unsigned port,const char *fixture_root);
int rkap_host_network_ready(void);
void rkap_host_after_apply(void);
#endif
#endif
