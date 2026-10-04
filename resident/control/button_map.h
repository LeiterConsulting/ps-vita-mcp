#ifndef VITA_CONTROL_BUTTON_MAP_H
#define VITA_CONTROL_BUTTON_MAP_H
#include <stdint.h>
/* Wire inputs name the Vita's legacy L/R triggers. Driver emulation uses L1/R1. */
static inline uint32_t rc_driver_buttons(uint32_t vita) {
    return (vita&~0x300u)|((vita&0x300u)<<2);
}
/* Keep effective-input telemetry and synthetic-activity filtering in wire units. */
static inline uint32_t rc_vita_buttons(uint32_t driver) {
    return (driver&~0xc00u)|((driver&0xc00u)>>2);
}
#endif
