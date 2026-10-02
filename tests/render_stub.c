/* Count buffered drawing calls in host tests; no physical display is involved. */
#include "platform.h"
unsigned test_draw_calls;
void draw_rect(float x,float y,float w,float h,uint32_t color) { (void)x;(void)y;(void)w;(void)h;(void)color;test_draw_calls++; }
void draw_circle(float x,float y,float r,uint32_t color) { (void)x;(void)y;(void)r;(void)color;test_draw_calls++; }
void draw_line(float x,float y,float x2,float y2,uint32_t color) { (void)x;(void)y;(void)x2;(void)y2;(void)color;test_draw_calls++; }
void draw_text(float x,float y,float scale,uint32_t color,const char *text) { (void)x;(void)y;(void)scale;(void)color;(void)text;test_draw_calls++; }
