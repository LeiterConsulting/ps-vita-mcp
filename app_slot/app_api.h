#ifndef VITA_APP_SLOT_API_H
#define VITA_APP_SLOT_API_H
#include <stdint.h>
#include <vita2d.h>

/* Version 1 of the fixed VMCP00001 development-slot module API. The harness
   owns network/authentication, identity, lifecycle, the font and presentation.
   Application code owns its resources and must return from every callback. */
typedef struct {
    float dt;
    uint32_t buttons, pressed;
    uint8_t lx, ly, rx, ry;
    int controller_result;
} AppSlotInput;
int app_init(void);
/* Return nonzero only while application state invariants remain healthy.
   Failure is sticky in the harness and leaves authenticated exit available. */
int app_update(const AppSlotInput *input);
void app_draw(vita2d_pgf *font);
int app_selftest(void);
void app_cleanup(void);
#endif
