#include "ui.h"
#include <stdarg.h>
#include <stdio.h>
#include <math.h>
void textf(float x,float y,float scale,uint32_t c,const char *format,...) {
    char buffer[256]; va_list args; va_start(args,format); vsnprintf(buffer,sizeof(buffer),format,args); va_end(args);
    draw_text(x,y,scale,c,buffer);
}
void card(float x,float y,float w,float h,const char *title) {
    draw_rect(x,y,w,h,UI_CARD); draw_rect(x,y,3,h,UI_TEAL); draw_text(x+16,y+26,0.95f,UI_TEXT,title);
}
void header(const char *title,const char *subtitle,float fps) {
    draw_rect(0,0,960,4,UI_TEAL); draw_text(24,36,1.3f,UI_TEXT,title);
    draw_text(24,61,0.8f,UI_MUTED,subtitle); textf(820,36,0.85f,UI_TEAL,"%.1f FPS",fps);
}
void footer(const char *a,const char *b) {
    draw_rect(0,490,960,54,COLOR(14,24,38));
    draw_text(24,512,0.76f,UI_MUTED,a); draw_text(24,535,0.76f,UI_MUTED,b);
}
void ring(float x,float y,float radius,uint32_t c) {
    const float tau=6.283185307f;
    for(int n=0;n<48;n++) {
        float a=tau*n/48,b=tau*(n+1)/48;
        draw_line(x+cosf(a)*radius,y+sinf(a)*radius,x+cosf(b)*radius,y+sinf(b)*radius,c);
    }
}
bool exit_combo(const Input *i) { return (i->buttons&(BTN_START|BTN_SELECT))==(BTN_START|BTN_SELECT); }
