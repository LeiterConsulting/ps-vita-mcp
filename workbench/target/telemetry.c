#include "telemetry.h"
#include <stdio.h>
void target_sample(TargetState *s,const Input *input,uint64_t ms) {
    s->input=*input; s->frame++; s->sampled_ms=ms;
    if(input->resumed) s->resumes++;
    s->buttons_seen|=input->buttons;
    int active=input->buttons||input->front.count||input->back.count;
    if(active) {
        s->active_frames++; s->last_buttons=input->buttons;
        s->last_sticks[0]=input->lx;s->last_sticks[1]=input->ly;s->last_sticks[2]=input->rx;s->last_sticks[3]=input->ry;
    } else if(s->active_frames) s->neutral_frames++;
    for(int i=0;i<input->front.count;i++) if(input->front.points[i].id==112) { s->front_seen++;s->front_x=input->front.points[i].raw_x;s->front_y=input->front.points[i].raw_y; }
    for(int i=0;i<input->back.count;i++) if(input->back.points[i].id==112) { s->rear_seen++;s->rear_x=input->back.points[i].raw_x;s->rear_y=input->back.points[i].raw_y; }
}
int target_json(const TargetState *s,char *out,unsigned cap,int pid,const char *run,const char *build) {
    return snprintf(out,cap,"{\"app\":\"Vita Input Target\",\"title_id\":\"CHRS00012\",\"version\":\"01.00\",\"protocol\":1,\"pid\":%d,\"run\":\"%s\",\"build_id\":\"%s\",\"frame\":%llu,\"sampled_ms\":%llu,\"resumes\":%llu,\"active_frames\":%llu,\"neutral_frames\":%llu,\"buttons\":%u,\"buttons_seen\":%u,\"last_buttons\":%u,\"sticks\":[%u,%u,%u,%u],\"last_sticks\":[%u,%u,%u,%u],\"front_seen\":%d,\"rear_seen\":%d,\"front\":[%d,%d],\"rear\":[%d,%d],\"ctrl_result\":%d,\"front_result\":%d,\"rear_result\":%d,\"fps\":%.2f}",pid,run,build,(unsigned long long)s->frame,(unsigned long long)s->sampled_ms,(unsigned long long)s->resumes,(unsigned long long)s->active_frames,(unsigned long long)s->neutral_frames,s->input.buttons,s->buttons_seen,s->last_buttons,s->input.lx,s->input.ly,s->input.rx,s->input.ry,s->last_sticks[0],s->last_sticks[1],s->last_sticks[2],s->last_sticks[3],s->front_seen,s->rear_seen,s->front_x,s->front_y,s->rear_x,s->rear_y,s->input.ctrl_result,s->input.front.read_result,s->input.back.read_result,s->input.fps);
}
