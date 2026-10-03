#ifndef VITA_RESIDENT_PLATFORM_H
#define VITA_RESIDENT_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
#ifdef __vita__
#include <psp2/kernel/clib.h>
#define R_MEMCPY sceClibMemcpy
#define R_MEMSET sceClibMemset
#define R_MEMMOVE sceClibMemmove
#define R_STRCMP sceClibStrcmp
#define R_STRNCMP sceClibStrncmp
#define R_STRCHR sceClibStrchr
#define R_STRSTR sceClibStrstr
#define R_SNPRINTF sceClibSnprintf
#define R_STRLEN(s) sceClibStrnlen((s),8192)
#else
#include <string.h>
#include <stdio.h>
#define R_MEMCPY memcpy
#define R_MEMSET memset
#define R_MEMMOVE memmove
#define R_STRCMP strcmp
#define R_STRNCMP strncmp
#define R_STRCHR strchr
#define R_STRSTR strstr
#define R_SNPRINTF snprintf
#define R_STRLEN strlen
#endif
#define R_PORT 17866
#ifndef R_BUILD_ID
#define R_BUILD_ID "host-fixture"
#endif
#define R_MAX_FILE (8u*1024u*1024u)
#define R_CHUNK 16384
typedef struct { int battery,charging,cpu,bus,gpu,xbar,network; } RDevice;
uint64_t r_now(void);
void r_delay(unsigned ms);
int r_running(void);
void r_log(const char *message,int result);
int r_network_init(void);
int r_network_ready(void);
void r_network_end(void);
int r_listen(void);
int r_accept(int socket); /* -1: would block, -2: broken listener */
int r_recv(int socket,void *buffer,size_t size); /* -2: would block */
int r_send(int socket,const void *buffer,size_t size);
void r_close_socket(int socket);
void r_device(RDevice *device);
int r_dir(const char *path); /* mkdir exclusive: 0 created, <0 exists/error */
int r_directory_exists(const char *path);
int r_open_write(const char *path); /* exclusive create */
int r_open_read(const char *path);
int r_write(int fd,const void *data,size_t size);
int r_read(int fd,void *data,size_t size);
int r_close_file(int fd);
int r_file_size(const char *path,uint64_t *size);
int r_rename(const char *from,const char *to);
void r_service(const char token[33]);
#endif
