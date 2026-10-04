#ifndef VITA_CONTROL_RLE_H
#define VITA_CONTROL_RLE_H
#include <stddef.h>
#include <stdint.h>
/* RGB packets: 0..127 = 1..128 literal pixels, 128..255 = 2..129 copies.
   Worst case adds one byte per 128 pixels. No allocation or lossy conversion. */
size_t rc_rle_encode(const unsigned char *rgb,size_t bytes,unsigned char *out,size_t capacity);
#define RC_RLE_MAGIC 0x31454c52u
typedef struct { uint32_t magic,bytes,encoding_us; } RRleHeader;
#endif
