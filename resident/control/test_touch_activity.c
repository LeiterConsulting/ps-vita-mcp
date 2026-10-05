#include "touch_activity.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    RTState s={0};assert(rt_panels(&s,77,1000)==0);
    /* A driver's clock may be ahead of, or far behind, the kernel clock. */
    rt_observe(&s,0,77,1,900000000000ULL,1000);assert(rt_panels(&s,77,1010)==1);
    rt_observe(&s,1,77,2,17,1005);assert(rt_panels(&s,77,1010)==3);
    /* Shell polling cannot replace the foreground reader, even with contacts. */
    rt_observe(&s,0,88,0,900000000001ULL,1010);assert(rt_panels(&s,77,1010)==3);
    rt_observe(&s,0,88,1,900000000002ULL,1011);assert(rt_panels(&s,77,1011)==3);
    assert(rt_panels(&s,99,1011)==0);
    /* Duplicate and out-of-order buffered samples must expire on their own. */
    rt_observe(&s,0,77,1,900000000000ULL,1300);assert(rt_panels(&s,77,1300)==0);
    rt_observe(&s,0,77,1,899999999999ULL,1301);assert(rt_panels(&s,77,1301)==0);
    assert(rt_reader(&s,0,77)->advances==1&&rt_reader(&s,0,77)->reads==3);
    assert(rt_reader(&s,0,77)->source_ticks==900000000000ULL);
    /* Advancing held contacts keep restoring, then fresh release clears them. */
    for(unsigned t=1302;t<9302;t+=100) {
        rt_observe(&s,0,77,1,900000000000ULL+t,t);assert(rt_panels(&s,77,t+90)==1);
    }
    rt_observe(&s,0,77,0,900000010000ULL,9302);assert(rt_panels(&s,77,9302)==0);
    /* Invalid inputs and zero source timestamps cannot invent activity. */
    rt_observe(&s,2,77,1,900000010001ULL,9303);
    rt_observe(&s,0,-1,1,900000010001ULL,9303);
    rt_observe(&s,0,77,9,900000010001ULL,9303);
    rt_observe(&s,0,77,1,0,9303);assert(rt_panels(&s,77,9303)==0);
    rt_observe(&s,0,77,1,900000010001ULL,9304);assert(rt_panels(&s,77,9303)==0);
    assert(rt_panels(&s,77,9555)==0);
    /* Bounded cache eviction fails closed for an evicted reader. */
    for(int pid=100;pid<104;pid++) rt_observe(&s,0,pid,0,1,9400+pid);
    assert(!rt_reader(&s,0,77));assert(rt_panels(&s,77,9555)==0);
    assert(s.last_pid[0]==103&&s.reads[0]>80);
    /* ID 112 is valid hardware unless it also matches active emulation. */
    assert(!rt_synthetic(112,500,500,0,112,500,500));
    assert(!rt_synthetic(112,600,500,1,112,500,500));
    assert(rt_synthetic(112,500,500,1,112,500,500));
    puts("touch activity: independent clocks, reader isolation, held contacts, release, stale expiry, bounds, diagnostics and synthetic exclusion passed");return 0;
}
