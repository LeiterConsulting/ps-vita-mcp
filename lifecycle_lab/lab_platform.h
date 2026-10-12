#ifndef VITA_LIFECYCLE_LAB_PLATFORM_H
#define VITA_LIFECYCLE_LAB_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
uint64_t lp_now(void);
void lp_delay(unsigned ms);
int lp_init(void);
void lp_end(void);
int lp_token(char token[33]);
int lp_nonce(unsigned char nonce[16]);
int lp_pid(void);
int lp_listen(void);
int lp_accept(int socket);
int lp_recv(int socket,void *data,size_t size);
int lp_send(int socket,const void *data,size_t size);
int lp_close(int socket);
int lp_thread_start(int (*worker)(void));
int lp_thread_join(void);
void lp_lock(void);
void lp_unlock(void);
#endif
