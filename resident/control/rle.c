#include "rle.h"
static int same(const unsigned char *a,const unsigned char *b) { return a[0]==b[0]&&a[1]==b[1]&&a[2]==b[2]; }
size_t rc_rle_encode(const unsigned char *rgb,size_t bytes,unsigned char *out,size_t capacity) {
    if(!rgb||!out||!bytes||bytes%3) return 0;
    size_t pixels=bytes/3,i=0,n=0;
    while(i<pixels) {
        size_t run=1;
        while(run<129&&i+run<pixels&&same(rgb+3*i,rgb+3*(i+run))) run++;
        if(run>=2) {
            if(capacity-n<4) return 0;
            out[n++]=(unsigned char)(128+run-2);
            for(unsigned c=0;c<3;c++) out[n++]=rgb[3*i+c];
            i+=run;
        } else {
            size_t begin=i++;
            while(i<pixels&&i-begin<128) {
                if(i+1<pixels&&same(rgb+3*i,rgb+3*(i+1))) break;
                i++;
            }
            size_t count=i-begin;
            if(capacity-n<1+count*3) return 0;
            out[n++]=(unsigned char)(count-1);
            for(size_t p=3*begin;p<3*i;p++) out[n++]=rgb[p];
        }
    }
    return n;
}
