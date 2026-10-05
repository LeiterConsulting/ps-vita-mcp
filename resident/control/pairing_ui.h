#ifndef VITA_PAIRING_UI_H
#define VITA_PAIRING_UI_H
#ifdef PU_HOST_TEST
#include "test_pairing_ui_platform.h"
#else
#include <vita2d.h>
#endif
void pu_init(void);
void pu_input(unsigned held,unsigned pressed,int valid);
int pu_active(void);
void pu_draw(vita2d_pgf *font);
void pu_shutdown(void);
#endif
