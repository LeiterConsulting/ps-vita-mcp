#ifndef VITA_LAB_PLATFORM_H
#define VITA_LAB_PLATFORM_H
#include <stdbool.h>
#include <stdint.h>
#define SCREEN_W 960
#define SCREEN_H 544
#define MAX_TOUCHES 8
#define COLOR(r,g,b) ((uint32_t)(r) | ((uint32_t)(g)<<8) | ((uint32_t)(b)<<16) | 0xff000000u)
enum { BTN_SELECT=1u, BTN_START=8u, BTN_UP=16u, BTN_RIGHT=32u,
       BTN_DOWN=64u, BTN_LEFT=128u, BTN_L=256u, BTN_R=512u,
       BTN_TRIANGLE=4096u, BTN_CIRCLE=8192u, BTN_CROSS=16384u, BTN_SQUARE=32768u };
typedef struct { float x,y,z; } Vec3;
typedef struct { unsigned id; float x,y; int raw_x,raw_y; } Contact;
typedef struct { int count,read_result,panel_result,start_result; Contact points[MAX_TOUCHES]; } TouchPanel;
typedef struct {
    uint32_t buttons,pressed;
    unsigned char lx,ly,rx,ry;
    int ctrl_result,motion_result,motion_start_result;
    Vec3 acceleration,gyro;
    TouchPanel front,back;
    float dt,fps;
    bool resumed;
} Input;
bool platform_init(void);
void platform_poll(Input *input);
void platform_begin(void);
void platform_end(void);
void platform_shutdown(void);
bool platform_should_exit(void);
void draw_rect(float x,float y,float w,float h,uint32_t color);
void draw_circle(float x,float y,float r,uint32_t color);
void draw_line(float x1,float y1,float x2,float y2,uint32_t color);
void draw_text(float x,float y,float scale,uint32_t color,const char *text);
#endif
