#include "telemetry.h"
#include "protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int parse(const char *input) {
    char buffer[2049];size_t n=strlen(input);assert(n<sizeof(buffer));memcpy(buffer,input,n+1);return target_authorize(buffer,n,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
}
int main(void) {
    const char *good="GET /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n\r\n";
    assert(parse(good)==200);assert(parse("GET /status HTTP/1.1\r\nHost: vita\r\n\r\n")==401);
    assert(parse("POST /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n\r\n")==404);
    assert(parse("GET /status HTTP/1.1\r\nAuthorization: Bearer bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\r\n\r\n")==401);
    assert(parse("GET /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n\r\n")==401);
    assert(parse("GET /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\nTransfer-Encoding: chunked\r\n\r\n")==400);
    assert(parse("GET /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\nContent-Length: 1\r\n\r\nx")==400);
    assert(parse("GET /status HTTP/1.1\r\nAuthorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n")==400);
    assert(parse("GET /status HTTP/1.1\r\n Authorization: Bearer aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n\r\n")==400);
    char nul[256];size_t n=strlen(good);memcpy(nul,good,n+1);nul[10]=0;assert(target_authorize(nul,n,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")==400);
    TargetState s={0};Input in={0};in.lx=64;in.ly=192;in.rx=192;in.ry=64;in.buttons=BTN_CROSS;
    in.front.count=1;in.front.points[0]=(Contact){112,0,0,700,400};in.back.count=1;in.back.points[0]=(Contact){112,0,0,1300,700};target_sample(&s,&in,1000);
    assert(s.front_seen==1&&s.rear_seen==1&&s.active_frames==1&&s.last_sticks[2]==192&&s.buttons_seen==BTN_CROSS);
    in.buttons=0;in.front.count=in.back.count=0;in.resumed=true;target_sample(&s,&in,1100);
    assert(s.neutral_frames==1&&s.resumes==1&&s.front_x==700&&s.rear_y==700&&s.last_buttons==BTN_CROSS);
    char json[2048];int size=target_json(&s,json,sizeof(json),77,"12345678901234567890123456789012","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    assert(size>0&&size<(int)sizeof(json)&&strstr(json,"\"neutral_frames\":1")&&strstr(json,"\"front\":[700,400]"));
    puts("Target actual HTTP auth/framing parser and latched input/resume telemetry: PASS (hardware adapters not exercised)");
}
