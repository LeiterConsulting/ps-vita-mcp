#ifndef DEVLOOP_SHA256_H
#define DEVLOOP_SHA256_H
#include <stddef.h>
void dev_sha256(const void *data,size_t size,char out[65]);
#endif
