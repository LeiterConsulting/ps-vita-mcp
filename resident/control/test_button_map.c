#include "button_map.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(rc_driver_buttons(0x100)==0x400);
    assert(rc_driver_buttons(0x200)==0x800);
    assert(rc_driver_buttons(0xf3f0)==0xfcf0);
    assert(rc_vita_buttons(0xfcf0)==0xf3f0);
    /* Every allowed wire combination must survive adaptation without introducing service buttons. */
    for(unsigned buttons=0;buttons<65536;buttons++) if(!(buttons&~0xf3f9u)) {
        unsigned driver=rc_driver_buttons(buttons);
        assert(!(driver&~0xfcf9u));assert(rc_vita_buttons(driver)==buttons);
        assert((driver&~0xc00u)==(buttons&~0x300u));
    }
    assert(rc_vita_buttons(0x100)==0x100); /* Already-normalized physical input. */
    assert(rc_vita_buttons(0x200)==0x200);
    puts("Vita shoulder/driver adaptation, combined masks, all allowed combinations and physical telemetry: PASS");
}
