#ifndef VITA_PAIRING_UI_H
#define VITA_PAIRING_UI_H
#include <vita2d.h>
void pu_init(void);
void pu_input(unsigned held,unsigned pressed,int valid);
int pu_active(void);
void pu_draw(vita2d_pgf *font);
void pu_shutdown(void);
#endif
