#include "pairing_client.h"
#include "control/pairing_privacy.h"
#include "control/pairing_approval.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint64_t ticks;
static const char *response;
static size_t offset;
static int closed,connected,send_fault,stall;
static char sent[2048];static size_t sent_size;
static uint64_t mono(void){return ticks;}
static void delay(unsigned n){ticks+=n;}
static int connect_fake(unsigned port){assert(port==17866);connected++;return 7;}
static int send_fake(int fd,const void *data,size_t n){assert(fd==7);if(send_fault)return -1;if(n>13)n=13;assert(sent_size+n<sizeof(sent));memcpy(sent+sent_size,data,n);sent_size+=n;sent[sent_size]=0;return (int)n;}
static int recv_fake(int fd,void *data,size_t n){assert(fd==7);if(stall)return -2;size_t available=strlen(response)-offset;if(!available)return 0;if(n>available)n=available;if(n>11)n=11;memcpy(data,response+offset,n);offset+=n;return (int)n;}
static void close_fake(int fd){assert(fd==7);closed++;}
static const PCIO io={mono,delay,connect_fake,send_fake,recv_fake,close_fake};
static const char *admin="11111111111111111111111111111111",*phone="22222222222222222222222222222222";
static void reset(const char *text){ticks=offset=sent_size=0;closed=connected=send_fault=stall=0;response=text;memset(sent,0,sizeof(sent));}
int main(void) {
    char wire[6000],out[4096];const char *json="{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"authorized\":true}";
    snprintf(wire,sizeof(wire),"HTTP/1.1 200 Result\r\nContent-Length: %u\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n%s",(unsigned)strlen(json),json);
    reset(wire);assert(pc_authorized(&io,17866,admin,phone,1)==200&&closed==1&&connected==1);assert(strstr(sent,"POST /pairing/native/renew ")&&strstr(sent,phone));puts("PASS actual client handles fragmented bounded response and renewal receipt");
    const char *bad[]={"HTTP/1.1 302 Result\r\nLocation: http://other/\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}",
        "HTTP/1.1 200 Result\r\nContent-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}",
        "HTTP/1.1 200 Result\r\nContent-Length: 2\r\nContent-Type: text/html\r\n\r\n{}",
        "HTTP/1.1 200 Result\r\nTransfer-Encoding: chunked\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}",
        "HTTP/1.1 200 Result\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}x",
        "HTTP/1.1 200 Result\r\nContent-Length: 9\r\nContent-Type: application/json\r\n\r\n{}",
        "HTTP/1.1 200 Result\r\nContent-Length: 4096\r\nContent-Type: application/json\r\n\r\n{}"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){reset(bad[i]);assert(pc_call(&io,17866,admin,"/pairing/ui/poll","{\"protocol\":1}",out)==0&&out[0]==0&&connected==1&&closed==1);}puts("PASS redirects, duplicate framing, extra/truncated bodies and bounds refused");
    reset(wire);stall=1;assert(pc_authorized(&io,17866,admin,phone,1)==503&&ticks==1500&&connected==1&&closed==1);reset(wire);send_fault=1;assert(pc_authorized(&io,17866,admin,phone,1)==503&&connected==1&&closed==1);puts("PASS interrupted exchange is bounded and never retries uncertain POST");
    reset("HTTP/1.1 200 Result\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}");assert(pc_authorized(&io,17866,admin,phone,1)==503);puts("PASS 200 without exact native authority receipt grants no phone access");
    char title[32]={0};strcpy(title,"CHRS00011");assert(!rc_pairing_process_allowed(0,title));strcpy(title,"CHRS00012");assert(rc_pairing_process_allowed(0,title)&&!rc_pairing_process_allowed(-1,title));memset(title,'a',32);assert(!rc_pairing_process_allowed(0,title));memset(title,0,32);assert(!rc_pairing_process_allowed(0,title));puts("PASS shared privacy decision denies Starter, unknown and unterminated process titles");
    PAArm arm={0};assert(!pa_cross(&arm,1000,1,1,0x4000,0x4000,0x4000));assert(!pa_cross(&arm,1100,1,1,0,0,0x4000));assert(!pa_cross(&arm,1599,1,1,0x4000,0x4000,0x4000));assert(!pa_cross(&arm,1600,1,1,0,0,0x4000));assert(pa_cross(&arm,2100,1,1,0x4000,0x4000,0x4000));assert(!pa_cross(&arm,2101,1,1,0x4000,0,0x4000));assert(!pa_cross(&arm,2200,1,0,0,0,0x4000));assert(!pa_cross(&arm,2800,1,1,0x4000,0x4000,0x4000));puts("PASS approval needs valid neutral samples for 500 ms and a fresh CROSS edge");
    puts("6 actual client/privacy/approval groups passed; SDK lookups and physical UI remain unqualified.");return 0;
}
