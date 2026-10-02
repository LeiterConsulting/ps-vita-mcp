#include "math_helpers.h"
#include <math.h>
float clampf(float v,float lo,float hi) { return v<lo?lo:(v>hi?hi:v); }
float axis_raw(unsigned char raw) { return raw>=128?(raw-128)/127.0f:(raw-128)/128.0f; }
float axis_deadzone(unsigned char raw,float dz) {
    float v=axis_raw(raw), a=fabsf(v);
    dz=clampf(dz,0.0f,0.95f);
    if(a<=dz) return 0;
    return copysignf((a-dz)/(1-dz),v);
}
float normalize_touch(int c,int lo,int hi) { return hi>lo?clampf((float)(c-lo)/(hi-lo),0,1):0.5f; }
