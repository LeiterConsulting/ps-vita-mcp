#include "platform.h"
#include "ui.h"
#include "core.h"
#include "server_vita.h"
#include <psp2/kernel/processmgr.h>
#include <string.h>

int main(void) {
    if(!platform_init()) return 1;
    DevCore core; dev_init(&core); bool network=dev_server_start();
    dev_log(&core,network?"Network listener started":"Network initialization failed; local controls available");
    char address[80]=""; unsigned count=0;
    while(!platform_should_exit()) {
        Input in; platform_poll(&in); if(exit_combo(&in)) break;
        dev_tick(&core,&in,sceKernelGetProcessTimeWide()/1000); dev_server_apply_pending(&core);
        if(count++%60==0) dev_server_address(address,sizeof(address));
        World *w=&core.world; bool brake=in.back.count>0||(in.buttons&BTN_CIRCLE);
        platform_begin();
        header("Vita DevLoop",network?address:"Network unavailable",in.fps);
        textf(410,53,0.74f,dev_server_paired()?UI_TEAL:UI_RED,"PAIRING %s | REV %u | FRAME %llu",dev_server_paired()?"READY":"MISSING",core.revision,(unsigned long long)core.frame);
        if(core.script.active) {
            DevScriptInfo *s=&core.script;
            textf(24,83,0.73f,s->faulted?UI_RED:UI_MUTED,"LUA %s | %s | %.8s | MEM %u KiB | UPDATE %.2f ms",s->name,s->faulted?"FAULTED":core.paused?"PAUSED":"RUNNING",s->sha256,s->memory_bytes/1024,s->update_ms);
            script_render();
            if(s->faulted) {
                draw_rect(24,175,912,230,UI_CARD); draw_text(44,213,1.1f,UI_RED,"Lua experiment paused after an error");
                textf(44,251,0.72f,UI_TEXT,"%.90s",s->error);
                if(strlen(s->error)>90) textf(44,278,0.72f,UI_TEXT,"%.90s",s->error+90);
                if(strlen(s->error)>180) textf(44,305,0.72f,UI_TEXT,"%.75s",s->error+180);
                draw_text(44,353,0.8f,UI_MUTED,"MCP: rollback, restart, load a fix, or return to native mode");
            } else if(core.paused) {
                draw_rect(630,420,280,44,COLOR(12,23,37)); draw_text(644,449,0.82f,UI_GOLD,"PAUSED - MCP resume / START");
            }
            footer("Live Lua | START pause / resume | START + SELECT exit",
                   "MCP: load source, inspect metrics, restart, rollback, or switch to native");
        } else {
        textf(24,83,0.73f,UI_MUTED,"%s | G %.0f  DRAG %.2f  BRAKE %.1f  SPEED %.0f | SCORE %d",core.paused?"PAUSED":"RUNNING",core.params.gravity,core.params.drag,core.params.brake,core.params.max_speed,w->score);
        draw_rect(w->left,w->top,w->right-w->left,w->bottom-w->top,UI_CARD);
        for(int x=70;x<930;x+=40) draw_line(x,94,x,474,COLOR(27,43,61));
        for(int y=114;y<474;y+=40) draw_line(30,y,930,y,COLOR(27,43,61));
        ring(w->goal_x,w->goal_y,w->goal_radius,UI_GOLD); ring(w->goal_x,w->goal_y,w->goal_radius-5,UI_GOLD);
        for(int n=0;n<w->obstacle_count;n++) { Obstacle o=w->obstacles[n]; draw_rect(o.x,o.y,o.w,o.h,n<3?COLOR(80,102,129):COLOR(124,104,196)); }
        draw_circle(w->x+3,w->y+4,w->radius,COLOR(9,18,30)); draw_circle(w->x,w->y,w->radius,brake?UI_GOLD:UI_TEAL);
        draw_circle(w->x-4,w->y-4,3,COLOR(222,255,247)); draw_line(w->x,w->y,w->x+core.force_x*30,w->y+core.force_y*30,UI_TEXT);
        if(core.paused) { draw_rect(320,220,320,100,COLOR(12,23,37)); draw_text(405,257,1.2f,UI_GOLD,"PAUSED"); draw_text(351,292,0.82f,UI_MUTED,"MCP resume or press START"); }
        footer("START pause | CROSS reset | SELECT recenter | SQUARE tilt / stick | TRIANGLE clear blocks",
               "Touch adds blocks | Rear touch / CIRCLE brake | L / R invert | START + SELECT exit");
        }
        platform_end(); dev_server_publish(&core);
    }
    dev_server_stop(); script_shutdown(); platform_shutdown(); return 0;
}
