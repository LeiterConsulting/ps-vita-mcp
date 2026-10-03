/* Streaming adaptation of this project's DevLoop SHA-256 implementation. */
#include "sha256.h"
#include <stdint.h>
#include "platform.h"
static uint32_t rotate(uint32_t x,unsigned n) { return (x>>n)|(x<<(32-n)); }
static void block(uint32_t h[8],const unsigned char p[64]) {
    static const uint32_t k[64]={
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for(unsigned n=0;n<16;n++) w[n]=((uint32_t)p[n*4]<<24)|((uint32_t)p[n*4+1]<<16)|((uint32_t)p[n*4+2]<<8)|p[n*4+3];
    for(unsigned n=16;n<64;n++) {
        uint32_t x=w[n-15],y=w[n-2];
        w[n]=w[n-16]+(rotate(x,7)^rotate(x,18)^(x>>3))+w[n-7]+(rotate(y,17)^rotate(y,19)^(y>>10));
    }
    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
    for(unsigned n=0;n<64;n++) {
        uint32_t t=v+(rotate(e,6)^rotate(e,11)^rotate(e,25))+((e&f)^((~e)&g))+k[n]+w[n];
        uint32_t u=(rotate(a,2)^rotate(a,13)^rotate(a,22))+((a&b)^(a&c)^(b&c));
        v=g; g=f; f=e; e=d+t; d=c; c=b; b=a; a=t+u;
    }
    h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=v;
}

void rs_init(RSha *s) {
    static const uint32_t initial[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    R_MEMSET(s,0,sizeof(*s)); R_MEMCPY(s->h,initial,sizeof(initial));
}
void rs_update(RSha *s,const void *data,size_t size) {
    const unsigned char *p=data; s->bytes+=size;
    while(size) {
        size_t n=64-s->used; if(n>size) n=size;
        R_MEMCPY(s->tail+s->used,p,n); s->used+=(unsigned)n; p+=n; size-=n;
        if(s->used==64) { block(s->h,s->tail); s->used=0; }
    }
}
void rs_final(RSha *s,char out[65]) {
    unsigned char tail[128]={0}; R_MEMCPY(tail,s->tail,s->used); tail[s->used]=128;
    size_t length=s->used<56?64:128; uint64_t bits=s->bytes*8;
    for(unsigned n=0;n<8;n++) tail[length-1-n]=(unsigned char)(bits>>(n*8));
    block(s->h,tail); if(length==128) block(s->h,tail+64);
    static const char hex[]="0123456789abcdef";
    for(unsigned n=0;n<32;n++) { unsigned char byte=(unsigned char)(s->h[n/4]>>(24-8*(n%4))); out[n*2]=hex[byte>>4]; out[n*2+1]=hex[byte&15]; }
    out[64]=0;
}
