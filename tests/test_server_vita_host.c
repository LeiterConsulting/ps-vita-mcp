#define _DEFAULT_SOURCE
#define DEVLOOP_SERVER_HOST_TEST
#ifndef DEVLOOP_SERVER_SOURCE
#define DEVLOOP_SERVER_SOURCE "../devloop/server_vita.c"
#endif
#include DEVLOOP_SERVER_SOURCE
#include "sha256.h"

static DevCore core;
static void *serve(void *argument) { int s=*(int*)argument; handle(s); close(s); return NULL; }
static void setup(void) {
    memset(&server,0,sizeof(server)); server.mutex=sceKernelCreateMutex("host-test",0,0,NULL); server.thread=server.listener=-1;
    server.running=server.paired=true; memset(server.token,'0',32); server.token[32]=0;
    server.pixels=malloc(SCREEN_W*SCREEN_H*4); assert(server.pixels);
    dev_init(&core); core.frame=40; core.sampled_ms=now_ms(); core.input.motion_result=0;
    dev_server_publish(&core);
}
/* Exercise actual server code over real local socketpairs. Mode 1 pumps commands
 * before rendering/publication; mode 2 requests capture; mode 3 forces expiry;
 * mode 4 simulates a resume; mode 5 leaves the main loop unavailable. */
static int exchange(const char *wire,size_t bytes,int mode,char *reply,size_t capacity) {
    int pair[2]; assert(!socketpair(AF_UNIX,SOCK_STREAM,0,pair)); assert(nonblocking(pair[1])>=0);
    struct timeval timeout={4,0}; assert(!setsockopt(pair[0],SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout)));
    pthread_t thread; assert(!pthread_create(&thread,NULL,serve,&pair[1]));
    /* Split every request so recv parsing has to handle header/body fragments. */
    size_t first=bytes>17?17:bytes; assert(send(pair[0],wire,first,MSG_NOSIGNAL)==(ssize_t)first);
    usleep(2000); if(bytes>first) assert(send(pair[0],wire+first,bytes-first,MSG_NOSIGNAL)==(ssize_t)(bytes-first));
    shutdown(pair[0],SHUT_WR);
    if(mode) {
        uint64_t deadline=now_ms()+800; bool queued=false;
        do { lock(); queued=server.pending==1; unlock(); if(!queued) usleep(1000); } while(!queued&&now_ms()<deadline);
        assert(queued); core.frame++; core.sampled_ms=now_ms();
        if(mode==3) { lock(); server.queued_ms=now_ms()-1100; unlock(); }
        if(mode==4) core.input.resumed=true;
        if(mode==2) dev_server_publish(&core);
        else if(mode!=5) dev_server_apply_pending(&core);
        core.input.resumed=false;
    }
    size_t used=0; int n;
    while((n=(int)recv(pair[0],reply+used,capacity-used-1,0))>0) { used+=(size_t)n; assert(used<capacity-1); }
    assert(n==0); reply[used]=0; close(pair[0]); assert(!pthread_join(thread,NULL));
    int code=0; assert(sscanf(reply,"HTTP/1.1 %d",&code)==1); return code;
}
static int get(const char *path,char *reply,size_t cap) {
    char request_text[256]; snprintf(request_text,sizeof(request_text),"GET %s HTTP/1.1\r\nAuthorization: Bearer %s\r\n\r\n",path,server.token);
    return exchange(request_text,strlen(request_text),0,reply,cap);
}
static int post(const char *path,const char *body,int mode,char *reply,size_t cap) {
    char request_text[1024]; snprintf(request_text,sizeof(request_text),"POST %s HTTP/1.1\r\nAuthorization: Bearer %s\r\nContent-Length: %u\r\n\r\n%s",path,server.token,(unsigned)strlen(body),body);
    return exchange(request_text,strlen(request_text),mode,reply,cap);
}
static int script_post(const char *name,const char *source,uint32_t revision,const char *extra,int mode,char *reply,size_t cap) {
    char hash[65]; dev_sha256(source,strlen(source),hash);
    size_t capacity=strlen(source)+1024; char *wire=malloc(capacity); assert(wire);
    int length=snprintf(wire,capacity,"POST /script HTTP/1.1\r\nAuthorization: Bearer %s\r\nContent-Type: text/x-lua\r\nX-DevLoop-Revision: %u\r\nX-DevLoop-Script-Name: %s\r\nX-DevLoop-Script-SHA256: %s\r\nContent-Length: %u\r\n%s\r\n%s",server.token,revision,name,hash,(unsigned)strlen(source),extra?extra:"",source);
    assert(length>0&&(size_t)length<capacity); int code=exchange(wire,(size_t)length,mode,reply,cap); free(wire); return code;
}
int main(void) {
    setup(); char reply[16384];
    assert(get("/status",reply,sizeof(reply))==200&&strstr(reply,"\"revision\":1")&&strstr(reply,"\"frame\":40"));
    assert(get("/input",reply,sizeof(reply))==200&&strstr(reply,"\"sticks\""));
    assert(get("/logs",reply,sizeof(reply))==200&&strstr(reply,"\"entries\""));
    puts("PASS actual native HTTP status/input/logs paths across fragmented socket reads");
    /* Force the exact observed ordering: acknowledge without calling end-of-frame
     * publish, then immediately read status. The pre-repair code returns rev 1. */
    assert(post("/control","expected_revision=1&action=resume",1,reply,sizeof(reply))==200&&strstr(reply,"\"revision\":2"));
    assert(get("/status",reply,sizeof(reply))==200);
    assert(strstr(reply,"\"revision\":2")&&strstr(reply,"\"frame\":41")&&strstr(reply,"\"paused\":false"));
    for(int n=0;n<1000;n++) {
        char body[96],marker[64]; snprintf(body,sizeof(body),"expected_revision=%u&action=pause",core.revision);
        assert(post("/control",body,1,reply,sizeof(reply))==200);
        snprintf(marker,sizeof(marker),"\"revision\":%u,\"frame\":%llu",core.revision,(unsigned long long)core.frame);
        assert(get("/status",reply,sizeof(reply))==200&&strstr(reply,marker));
    }
    puts("PASS regression: 1001 command acknowledgements remain visible to immediate reads before render publication");
    uint32_t previous=core.revision; float gravity=core.params.gravity;
    assert(post("/parameters","expected_revision=1&gravity=700",1,reply,sizeof(reply))==409&&core.revision==previous&&core.params.gravity==gravity);
    char body[96]; snprintf(body,sizeof(body),"expected_revision=%u&gravity=1501",core.revision);
    assert(post("/parameters",body,0,reply,sizeof(reply))==400&&core.params.gravity==gravity);
    snprintf(body,sizeof(body),"expected_revision=%u&action=resume",core.revision);
    assert(post("/control",body,3,reply,sizeof(reply))==503&&core.revision==previous&&core.paused);
    assert(post("/control",body,4,reply,sizeof(reply))==503&&core.revision==previous&&core.paused);
    assert(post("/control",body,5,reply,sizeof(reply))==503&&core.revision==previous&&server.pending==0);
    dev_server_apply_pending(&core); assert(core.revision==previous);
    puts("PASS actual native stale revision, invalid parameter, expiry/resume and cancelled unacknowledged commands");
    const struct { const char *wire; int code; } cases[]={
        {"GET /status HTTP/1.1\r\nHost: local\r\n\r\n",401},
        {"GET /status HTTP/1.1\r\nAuthorization: Bearer 11111111111111111111111111111111\r\n\r\n",401},
        {"GET /status HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nAuthorization: Bearer 00000000000000000000000000000000\r\n\r\n",401},
        {"GET /status HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nTransfer-Encoding: chunked\r\n\r\n",400},
        {"POST /control HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n",400},
        {"POST /control HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nContent-Length: 512\r\n\r\n",413},
        {"POST /control HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nContent-Length: 2\r\n\r\nx",400},
        {"GET /status HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\n\r\nx",400},
        {"DELETE /status HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\n\r\n",405}
    };
    core.sampled_ms=now_ms(); dev_server_publish(&core);
    for(unsigned n=0;n<sizeof(cases)/sizeof(cases[0]);n++) assert(exchange(cases[n].wire,strlen(cases[n].wire),0,reply,sizeof(reply))==cases[n].code);
    assert(get("/unknown",reply,sizeof(reply))==404);
    lock(); server.snapshot.sampled_ms=now_ms()-2000; unlock(); assert(get("/status",reply,sizeof(reply))==503);
    core.sampled_ms=now_ms(); dev_server_publish(&core);
    puts("PASS actual native authentication, duplicate headers, framing/size/method rejection and stale snapshots");
    size_t pitch=SCREEN_W+8; unsigned char *fb=calloc(SCREEN_H*pitch,4); assert(fb);
    for(int y=0;y<SCREEN_H;y++) { fb[(size_t)y*pitch*4]=(unsigned char)(y%256); fb[(size_t)y*pitch*4+1]=77; }
    shim_fb=(SceDisplayFrameBuf){sizeof(shim_fb),fb,(unsigned)pitch,0,SCREEN_W,SCREEN_H};
    char request_text[256]; snprintf(request_text,sizeof(request_text),"GET /screenshot HTTP/1.1\r\nAuthorization: Bearer %s\r\n\r\n",server.token);
    assert(exchange(request_text,strlen(request_text),2,reply,sizeof(reply))==500&&strstr(reply,"Screenshot encoding failed"));
    assert(shim_gpu_waits&&shim_queue_waits&&server.capture_frame==core.frame&&server.capture_revision==core.revision);
    for(int y=0;y<SCREEN_H;y++) assert(server.pixels[(size_t)y*SCREEN_W*4]==(unsigned char)(y%256)&&server.pixels[(size_t)y*SCREEN_W*4+1]==77&&server.pixels[(size_t)y*SCREEN_W*4+3]==255);
    shim_fb.pixelformat=7; assert(exchange(request_text,strlen(request_text),2,reply,sizeof(reply))==500&&strstr(reply,"Own framebuffer unavailable"));
    free(fb);
    puts("PASS actual native capture respects pitch/alpha, synchronizes GPU/display, and reports capture/encoder failures");
    const char *good="return {update=function(dt,input) vita.metric('buttons',input.buttons) end,draw=function() vita.circle(480,285,16,vita.rgb(64,220,191)) end}";
    core.sampled_ms=now_ms(); dev_server_publish(&core);
    previous=core.revision;
    assert(script_post("wire_script",good,previous,NULL,1,reply,sizeof(reply))==200&&strstr(reply,"\"active\":true")&&strstr(reply,"\"paused\":true"));
    assert(get("/script",reply,sizeof(reply))==200&&strstr(reply,"\"name\":\"wire_script\""));
    assert(core.revision==previous+1&&core.script.active);
    assert(script_post("conflict",good,previous,NULL,1,reply,sizeof(reply))==409);
    assert(script_post("bad","error('quoted \"error\"')",core.revision,NULL,1,reply,sizeof(reply))==422&&strstr(reply,"\\\"error\\\""));
    assert(get("/script",reply,sizeof(reply))==200&&strstr(reply,"\"name\":\"wire_script\""));
    puts("PASS actual native Lua upload, SHA-256, error escaping, preflight rejection and acknowledgement/read ordering");
    assert(script_post("bad/name",good,core.revision,NULL,0,reply,sizeof(reply))==400);
    assert(script_post("dup",good,core.revision,"X-DevLoop-Revision: 1\r\n",0,reply,sizeof(reply))==400);
    assert(script_post("dup",good,core.revision,"X-DevLoop-Script-SHA256: 0000000000000000000000000000000000000000000000000000000000000000\r\n",0,reply,sizeof(reply))==400);
    const char *missing="POST /script HTTP/1.1\r\nAuthorization: Bearer 00000000000000000000000000000000\r\nContent-Length: 1\r\n\r\nx";
    assert(exchange(missing,strlen(missing),0,reply,sizeof(reply))==400);
    char *full=malloc(SCRIPT_MAX+1); assert(full); memset(full,' ',SCRIPT_MAX); memcpy(full,good,strlen(good)); full[SCRIPT_MAX]=0;
    assert(script_post("max_size",full,core.revision,NULL,1,reply,sizeof(reply))==200&&core.script.source_bytes==SCRIPT_MAX); free(full);
    snprintf(body,sizeof(body),"expected_revision=%u&action=native",core.revision);
    assert(post("/control",body,1,reply,sizeof(reply))==200&&strstr(reply,"\"active\":false")&&core.paused);
    dev_server_stop(); script_shutdown();
    puts("PASS dedicated script header validation, maximum source transfer and native fallback through actual HTTP");
    puts("7 native-server host groups passed with POSIX substitutes and actual Lua; physical 01.02 acceptance is separate.");
    return 0;
}
