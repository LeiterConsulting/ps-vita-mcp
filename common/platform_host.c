// Headless rendering of the app's own drawing calls for layout inspection.
// Synthetic inputs here are preview fixtures, never evidence of Vita hardware.
#include "platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static FILE *svg;
static unsigned frame_count;
static const char *rgb(uint32_t c) {
    static char b[8]; snprintf(b,sizeof(b),"#%02x%02x%02x",c&255,(c>>8)&255,(c>>16)&255); return b;
}
bool platform_init(void) {
    const char *path=getenv("PREVIEW_PATH"); svg=fopen(path?path:"preview.svg","w"); return svg!=NULL;
}
void platform_poll(Input *in) {
    memset(in,0,sizeof(*in)); in->dt=1.0f/60; in->fps=60;
    in->lx=164; in->ly=98; in->rx=128; in->ry=128;
    in->ctrl_result=1; in->motion_result=0; in->front.read_result=in->back.read_result=1;
    in->buttons=BTN_CROSS|BTN_UP;
    in->acceleration=(Vec3){0.12f,0.42f,-0.88f}; in->gyro=(Vec3){0.01f,-0.08f,0.04f};
    in->front.count=2; in->front.points[0]=(Contact){1,0.2f,0.6f,384,652}; in->front.points[1]=(Contact){2,0.8f,0.3f,1535,326};
    in->back.count=1; in->back.points[0]=(Contact){3,0.45f,0.7f,864,680};
    if(getenv("PREVIEW_SENSOR_ERROR")) {
        in->motion_result=-1; in->front.count=0; in->front.read_result=-1;
        in->back.count=0; in->back.read_result=-1;
    }
}
void platform_begin(void) {
    fprintf(svg,"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"960\" height=\"544\" viewBox=\"0 0 960 544\"><rect width=\"960\" height=\"544\" fill=\"#0a111d\"/>\n");
}
void platform_end(void) { fprintf(svg,"</svg>\n"); frame_count++; }
bool platform_should_exit(void) { return frame_count>0; }
void platform_shutdown(void) { fclose(svg); }
void draw_rect(float x,float y,float w,float h,uint32_t c) { fprintf(svg,"<rect x=\"%.2f\" y=\"%.2f\" width=\"%.2f\" height=\"%.2f\" fill=\"%s\"/>\n",x,y,w,h,rgb(c)); }
void draw_circle(float x,float y,float r,uint32_t c) { fprintf(svg,"<circle cx=\"%.2f\" cy=\"%.2f\" r=\"%.2f\" fill=\"%s\"/>\n",x,y,r,rgb(c)); }
void draw_line(float x,float y,float x2,float y2,uint32_t c) { fprintf(svg,"<line x1=\"%.2f\" y1=\"%.2f\" x2=\"%.2f\" y2=\"%.2f\" stroke=\"%s\"/>\n",x,y,x2,y2,rgb(c)); }
void draw_text(float x,float y,float scale,uint32_t c,const char *t) {
    fprintf(svg,"<text x=\"%.2f\" y=\"%.2f\" font-size=\"%.2f\" font-family=\"Arial,sans-serif\" fill=\"%s\">",x,y,scale*20,rgb(c));
    for(;*t;t++) { if(*t=='&') fputs("&amp;",svg); else if(*t=='<') fputs("&lt;",svg); else if(*t=='>') fputs("&gt;",svg); else fputc(*t,svg); }
    fputs("</text>\n",svg);
}
