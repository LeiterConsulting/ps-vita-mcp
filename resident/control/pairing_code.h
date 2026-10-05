#ifndef VITA_PAIRING_CODE_H
#define VITA_PAIRING_CODE_H
#include <stddef.h>
#include <stdint.h>

/* Avoid depending on native printf padding/return conventions for an approval code. */
static inline int pu_code(int (*random)(void *,size_t),char out[7],int *random_result) {
    for(unsigned i=0;i<7;i++)out[i]=0;
    for(unsigned attempt=0;attempt<16;attempt++) {
        uint32_t value=0;*random_result=random(&value,sizeof(value));
        if(*random_result<0)return 0;
        if(value>=4294000000u)continue;
        value%=1000000u;
        for(int digit=5;digit>=0;digit--){out[digit]=(char)('0'+value%10u);value/=10u;}
        out[6]=0;return 1;
    }
    return 0;
}
#endif
