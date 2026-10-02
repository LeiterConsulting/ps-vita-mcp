#ifndef VITA_LAB_UI_H
#define VITA_LAB_UI_H
#include "platform.h"
#define UI_TEXT COLOR(232,239,249)
#define UI_MUTED COLOR(151,170,195)
#define UI_TEAL COLOR(64,220,191)
#define UI_GOLD COLOR(255,197,98)
#define UI_RED COLOR(255,108,126)
#define UI_CARD COLOR(20,32,49)
void textf(float x,float y,float scale,uint32_t color,const char *format,...);
void card(float x,float y,float w,float h,const char *title);
void header(const char *title,const char *subtitle,float fps);
void footer(const char *first,const char *second);
void ring(float x,float y,float radius,uint32_t color);
bool exit_combo(const Input *input);
#endif
