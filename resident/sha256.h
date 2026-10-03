#ifndef RESIDENT_SHA256_H
#define RESIDENT_SHA256_H
#include <stddef.h>
#include <stdint.h>
typedef struct { uint32_t h[8]; uint64_t bytes; unsigned used; unsigned char tail[64]; } RSha;
void rs_init(RSha *s);
void rs_update(RSha *s,const void *data,size_t size);
void rs_final(RSha *s,char out[65]);
#endif
