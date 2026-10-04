#include "rle.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char rgb[480*272*3],encoded[480*272*3+1020],decoded[480*272*3];
static size_t decode(size_t size) {
    size_t i=0,n=0;
    while(i<size) {
        unsigned tag=encoded[i++],count=tag<128?tag+1:tag-128+2;
        if(tag<128) { assert(size-i>=3*count); memcpy(decoded+n,encoded+i,3*count); i+=3*count; n+=3*count; }
        else { assert(size-i>=3); for(unsigned p=0;p<count;p++) { memcpy(decoded+n,encoded+i,3); n+=3; } i+=3; }
        assert(n<=sizeof(decoded));
    }
    return n;
}
int main(void) {
    unsigned char vector[]={1,2,3,1,2,3,4,5,6},answer[]={128,1,2,3,0,4,5,6};
    size_t n=rc_rle_encode(vector,sizeof(vector),encoded,sizeof(encoded)); assert(n==sizeof(answer)&&!memcmp(encoded,answer,n));
    assert(!rc_rle_encode(vector,sizeof(vector),encoded,n-1));
    assert(!rc_rle_encode(vector,8,encoded,sizeof(encoded))); assert(!rc_rle_encode(vector,0,encoded,sizeof(encoded)));
    uint32_t seed=0x12345678;
    for(unsigned mode=0;mode<4;mode++) {
        for(size_t i=0;i<sizeof(rgb);i++) { seed=1664525*seed+1013904223; rgb[i]=mode==0?42:mode==1?(unsigned char)(i%251):mode==2?(unsigned char)(seed>>24):(unsigned char)((i/300)%251); }
        for(size_t pixels=1;pixels<=sizeof(rgb)/3;pixels=pixels<260?pixels+1:pixels*2) {
            size_t bytes=pixels*3; n=rc_rle_encode(rgb,bytes,encoded,sizeof(encoded));
            assert(n&&n<=bytes+(pixels+127)/128); assert(decode(n)==bytes&&!memcmp(rgb,decoded,bytes));
        }
        n=rc_rle_encode(rgb,sizeof(rgb),encoded,sizeof(encoded)); assert(n&&decode(n)==sizeof(rgb)&&!memcmp(rgb,decoded,sizeof(rgb)));
    }
    puts("RLE independent decode, boundary vectors, worst case, random RGB and capacity: PASS");
}
