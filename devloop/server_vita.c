#include "server_vita.h"
#ifdef DEVLOOP_SERVER_HOST_TEST
#include "server_host_shim.h"
#else
#include <psp2/kernel/threadmgr.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/sysmodule.h>
#include <psp2/display.h>
#include <psp2/gxm.h>
#include <vita2d.h>
#include <png.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <setjmp.h>
#include <errno.h>

static struct {
    SceUID mutex,thread;
    int listener;
    bool running,paired,module,net,ctl,thread_started;
    void *net_memory;
    char token[33];
    DevCore snapshot;
    int pending,operation,result; /* 0 idle, 1 queued, 2 completed; operation 1 command, 2 capture */
    uint64_t queued_ms;
    DevCommand command;
    char reply[DEV_JSON_MAX];
    unsigned char *pixels;
    uint32_t capture_revision;
    uint64_t capture_frame,capture_ms;
} server;
static uint64_t now_ms(void) { return sceKernelGetProcessTimeWide()/1000; }
static void lock(void) { sceKernelLockMutex(server.mutex,1,NULL); }
static void unlock(void) { sceKernelUnlockMutex(server.mutex,1); }
static bool running(void) { lock(); bool value=server.running; unlock(); return value; }
static void error_json(char *out,size_t cap,const char *message) { dev_error_json(out,cap,message); }
static bool again(void) { int e=*sceNetErrnoLoc(); return e==SCE_NET_EAGAIN||e==SCE_NET_EWOULDBLOCK; }
static int nonblocking(int s) { int enabled=1; return sceNetSetsockopt(s,SCE_NET_SOL_SOCKET,SCE_NET_SO_NBIO,&enabled,sizeof(enabled)); }
static bool send_all(int s,const void *data,size_t length,uint64_t deadline) {
    const unsigned char *p=data;
    while(length&&running()&&now_ms()<deadline) {
        int n=sceNetSend(s,p,length,0);
        if(n>0) { p+=n; length-=(size_t)n; }
        else if(n<0&&again()) sceKernelDelayThread(1000);
        else return false;
    }
    return length==0;
}
static void response(int s,int code,const char *type,const void *body,size_t size,const char *extra) {
    char header[512];
    int n=snprintf(header,sizeof(header),"HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %u\r\nConnection: close\r\nCache-Control: no-store\r\n%s\r\n",code,code==200?"OK":"Error",type,(unsigned)size,extra?extra:"");
    uint64_t deadline=now_ms()+4000;
    if(n>0&&(size_t)n<sizeof(header)&&send_all(s,header,(size_t)n,deadline)) send_all(s,body,size,deadline);
}
static void failure(int s,int code,const char *message) { char body[1024]; error_json(body,sizeof(body),message); response(s,code,"application/json",body,strlen(body),NULL); }
static bool authorized(const char *value) {
    if(!server.paired||strlen(value)!=39||strncmp(value,"Bearer ",7)) return false;
    unsigned difference=0; for(int n=0;n<32;n++) difference|=(unsigned char)value[n+7]^(unsigned char)server.token[n];
    return difference==0;
}
/* Deliberately small HTTP subset: one request per connection, fixed length, no transfer encoding. */
static int request(int s,char *method,char *path,char *body,DevCommand *command) {
    char buffer[4097]; size_t used=0; char *end=NULL; uint64_t deadline=now_ms()+2500;
    while(!end&&used<4096&&running()&&now_ms()<deadline) {
        int n=sceNetRecv(s,buffer+used,4096-used,0);
        if(n>0) { used+=(size_t)n; buffer[used]=0; end=strstr(buffer,"\r\n\r\n"); }
        else if(n<0&&again()) sceKernelDelayThread(1000); else return 400;
    }
    if(!end) return 400;
    size_t header_size=(size_t)(end-buffer)+4;
    if(memchr(buffer,0,header_size)) return 400;
    *end=0; char *line_end=strstr(buffer,"\r\n"); if(!line_end) return 400;
    *line_end=0; char protocol[16],extra;
    if(sscanf(buffer,"%7s %63s %15s %c",method,path,protocol,&extra)!=3||strcmp(protocol,"HTTP/1.1")) return 400;
    bool script=!strcmp(method,"POST")&&!strcmp(path,"/script");
    bool auth_seen=false,length_seen=false,type_seen=false,revision_seen=false,name_seen=false,hash_seen=false; size_t length=0;
    for(char *line=line_end+2;*line;) {
        char *next=strstr(line,"\r\n"); if(next) *next=0;
        char *colon=strchr(line,':'); if(!colon) return 400; *colon++=0;
        while(*colon==' '||*colon=='\t') colon++;
        if(!strcasecmp(line,"Authorization")) { if(auth_seen||!authorized(colon)) return 401; auth_seen=true; }
        if(!strcasecmp(line,"Transfer-Encoding")) return 400;
        if(!strcasecmp(line,"Content-Length")) {
            if(length_seen||!*colon) return 400;
            length_seen=true;
            for(const char *p=colon;*p;p++) if(!isdigit((unsigned char)*p)) return 400;
            if(strlen(colon)>5) return 413;
            length=(size_t)strtoul(colon,NULL,10); if(length>(script?SCRIPT_MAX:511)) return 413;
        }
        if(!strcasecmp(line,"Content-Type")) {
            if(type_seen) return 400;
            type_seen=true;
            if(script&&strcmp(colon,"text/x-lua")) return 400;
        }
        if(!strcasecmp(line,"X-DevLoop-Revision")) {
            if(!script||revision_seen||!*colon||strlen(colon)>10) return 400;
            revision_seen=true;
            for(const char *p=colon;*p;p++) if(!isdigit((unsigned char)*p)) return 400;
            errno=0; unsigned long value=strtoul(colon,NULL,10);
            if(errno||!value||value>UINT32_MAX) return 400;
            command->expected_revision=(uint32_t)value;
        }
        if(!strcasecmp(line,"X-DevLoop-Script-Name")) {
            if(!script||name_seen||!*colon||strlen(colon)>32) return 400;
            name_seen=true;
            for(const char *p=colon;*p;p++) if(!isalnum((unsigned char)*p)&&*p!='_'&&*p!='-') return 400;
            snprintf(command->script_name,sizeof(command->script_name),"%s",colon);
        }
        if(!strcasecmp(line,"X-DevLoop-Script-SHA256")) {
            if(!script||hash_seen||strlen(colon)!=64) return 400;
            hash_seen=true;
            for(const char *p=colon;*p;p++) if(!strchr("0123456789abcdef",*p)) return 400;
            memcpy(command->script_sha256,colon,65);
        }
        if(!next) break;
        line=next+2;
    }
    if(!auth_seen) return 401;
    if(strcmp(method,"GET")&&strcmp(method,"POST")) return 405;
    if((!strcmp(method,"POST")&&!length_seen)||(!strcmp(method,"GET")&&length)) return 400;
    if(script&&(!length||!type_seen||!revision_seen||!name_seen||!hash_seen)) return 400;
    if(used>header_size+length) return 400;
    size_t body_used=used-header_size; memcpy(body,buffer+header_size,body_used);
    while(body_used<length&&running()&&now_ms()<deadline) {
        int n=sceNetRecv(s,body+body_used,length-body_used,0);
        if(n>0) body_used+=(size_t)n;
        else if(n<0&&again()) sceKernelDelayThread(1000); else return 400;
    }
    if(body_used!=length||memchr(body,0,length)) return 400;
    body[length]=0;
    if(script) { command->script_upload=true; memcpy(command->script_source,body,length+1); }
    return 200;
}
typedef struct { unsigned char *data; size_t size,capacity; } PngBuffer;
#ifndef DEVLOOP_SERVER_HOST_TEST
static void png_write(png_structp png,png_bytep data,png_size_t size) {
    PngBuffer *b=png_get_io_ptr(png);
    if(b->size+size>3*1024*1024) png_error(png,"PNG too large");
    if(b->size+size>b->capacity) {
        size_t capacity=b->capacity?b->capacity*2:65536;
        while(capacity<b->size+size) capacity*=2;
        unsigned char *p=realloc(b->data,capacity); if(!p) png_error(png,"Out of memory"); b->data=p; b->capacity=capacity;
    }
    memcpy(b->data+b->size,data,size); b->size+=size;
}
static void png_flush(png_structp png) { (void)png; }
static bool encode_png(PngBuffer *b) {
    png_structp png=png_create_write_struct(PNG_LIBPNG_VER_STRING,NULL,NULL,NULL); if(!png) return false;
    png_infop info=png_create_info_struct(png); if(!info) { png_destroy_write_struct(&png,NULL); return false; }
    if(setjmp(png_jmpbuf(png))) { png_destroy_write_struct(&png,&info); free(b->data); b->data=NULL; return false; }
    png_set_write_fn(png,b,png_write,png_flush);
    png_set_IHDR(png,info,SCREEN_W,SCREEN_H,8,PNG_COLOR_TYPE_RGBA,PNG_INTERLACE_NONE,PNG_COMPRESSION_TYPE_DEFAULT,PNG_FILTER_TYPE_DEFAULT);
    png_set_compression_level(png,1); png_write_info(png,info);
    for(int y=0;y<SCREEN_H;y++) png_write_row(png,server.pixels+(size_t)y*SCREEN_W*4);
    png_write_end(png,info); png_destroy_write_struct(&png,&info); return true;
}
#else
/* The host harness exercises framebuffer copy and the encoder-error path.
 * Real libpng output is covered by the native build and physical PNG evidence. */
static bool encode_png(PngBuffer *b) { (void)b; return false; }
#endif
static bool fresh(const DevCore *c) { uint64_t ms=now_ms(); return c->frame&&ms>=c->sampled_ms&&ms-c->sampled_ms<1500; }
static bool await_main(void) {
    uint64_t deadline=now_ms()+1200;
    while(running()&&now_ms()<deadline) {
        lock(); bool done=server.pending==2; unlock(); if(done) return true; sceKernelDelayThread(1000);
    }
    lock(); server.pending=0; unlock(); return false;
}
static void handle(int s) {
    char method[8],path[64],body[SCRIPT_MAX+1],json[DEV_JSON_MAX]; DevCommand command={0}; int code=request(s,method,path,body,&command);
    if(code!=200) { failure(s,code,code==401?"Pairing authorization required":"Malformed or unsupported HTTP request"); return; }
    lock(); DevCore snapshot=server.snapshot; unlock();
    if(!fresh(&snapshot)) { failure(s,503,"Device sample is stale; resume the DevLoop app"); return; }
    if(!strcmp(method,"GET")&&(!strcmp(path,"/status")||!strcmp(path,"/input")||!strcmp(path,"/logs")||!strcmp(path,"/script"))) {
        if(!strcmp(path,"/status")) dev_status_json(&snapshot,json,sizeof(json));
        if(!strcmp(path,"/input")) dev_input_json(&snapshot,json,sizeof(json));
        if(!strcmp(path,"/logs")) dev_logs_json(&snapshot,json,sizeof(json));
        if(!strcmp(path,"/script")) dev_script_json(&snapshot,json,sizeof(json));
        response(s,200,"application/json",json,strlen(json),NULL); return;
    }
    bool screenshot=!strcmp(method,"GET")&&!strcmp(path,"/screenshot");
    if(!screenshot&&!command.script_upload) {
        if(strcmp(method,"POST")||(strcmp(path,"/parameters")&&strcmp(path,"/control"))) { failure(s,404,"Unknown endpoint"); return; }
        char error[256]; code=dev_parse_command(path,body,&command,error,sizeof(error)); if(code!=200) { failure(s,code,error); return; }
    }
    lock(); server.command=command; server.operation=screenshot?2:1; server.queued_ms=now_ms(); server.pending=1; unlock();
    if(!await_main()) { failure(s,503,"Main loop did not acknowledge; read status before retrying any change"); return; }
    lock(); code=server.result; snprintf(json,sizeof(json),"%s",server.reply);
    uint32_t revision=server.capture_revision; uint64_t frame=server.capture_frame,ms=server.capture_ms; unlock();
    if(screenshot&&code==200) {
        PngBuffer png={0};
        if(encode_png(&png)) {
            char extra[192]; snprintf(extra,sizeof(extra),"X-DevLoop-Revision: %u\r\nX-DevLoop-Frame: %llu\r\nX-DevLoop-Sampled-Ms: %llu\r\n",revision,(unsigned long long)frame,(unsigned long long)ms);
            response(s,200,"image/png",png.data,png.size,extra); free(png.data);
        } else failure(s,500,"Screenshot encoding failed");
    } else response(s,code,"application/json",json,strlen(json),NULL);
    lock(); server.pending=0; unlock();
}
static int worker(SceSize args,void *argp) {
    (void)args; (void)argp;
    while(running()) {
        int s=sceNetAccept(server.listener,NULL,NULL);
        if(s<0) { sceKernelDelayThread(10000); continue; }
        if(nonblocking(s)>=0) handle(s);
        sceNetSocketClose(s);
    }
    return 0;
}
bool dev_server_start(void) {
    memset(&server,0,sizeof(server)); server.mutex=server.thread=server.listener=-1;
    FILE *cfg=fopen("ux0:data/vita-devloop/bridge.cfg","rb");
    if(cfg) {
        char token[64]={0}; size_t n=fread(token,1,63,cfg); fclose(cfg);
        while(n&&(token[n-1]=='\r'||token[n-1]=='\n')) token[--n]=0;
        bool valid=n==32; for(size_t i=0;i<n;i++) if(!strchr("0123456789abcdef",token[i])) valid=false;
        if(valid) { memcpy(server.token,token,33); server.paired=true; }
    }
    server.mutex=sceKernelCreateMutex("devloop-state",0,0,NULL); if(server.mutex<0) return false;
    server.pixels=malloc(SCREEN_W*SCREEN_H*4); if(!server.pixels) goto fail;
    if(sceSysmoduleLoadModule(SCE_SYSMODULE_NET)<0) goto fail;
    server.module=true;
    server.net_memory=malloc(1024*1024); if(!server.net_memory) goto fail;
    SceNetInitParam init={server.net_memory,1024*1024,0}; if(sceNetInit(&init)<0) goto fail; server.net=true;
    if(sceNetCtlInit()<0) goto fail;
    server.ctl=true;
    server.listener=sceNetSocket("devloop-http",SCE_NET_AF_INET,SCE_NET_SOCK_STREAM,0); if(server.listener<0) goto fail;
    int reuse=1; sceNetSetsockopt(server.listener,SCE_NET_SOL_SOCKET,SCE_NET_SO_REUSEADDR,&reuse,sizeof(reuse));
    SceNetSockaddrIn address={0}; address.sin_len=sizeof(address); address.sin_family=SCE_NET_AF_INET; address.sin_port=sceNetHtons(DEV_PORT); address.sin_addr.s_addr=sceNetHtonl(SCE_NET_INADDR_ANY);
    if(sceNetBind(server.listener,(SceNetSockaddr*)&address,sizeof(address))<0||sceNetListen(server.listener,4)<0||nonblocking(server.listener)<0) goto fail;
    server.running=true; server.thread=sceKernelCreateThread("devloop-http",worker,0x10000100,256*1024,0,0,NULL);
    if(server.thread<0||sceKernelStartThread(server.thread,0,NULL)<0) goto fail;
    server.thread_started=true;
    return true;
fail: dev_server_stop(); return false;
}
void dev_server_apply_pending(DevCore *c) {
    if(server.mutex<0) return;
    lock();
    if(server.pending==1&&server.operation==1) {
        if(c->input.resumed||now_ms()-server.queued_ms>1000) { server.result=503; error_json(server.reply,sizeof(server.reply),"Command expired or console resumed; read status before retrying"); }
        else {
            char error[256]; server.result=dev_apply(c,&server.command,error,sizeof(error));
            if(server.result==200) {
                if(server.command.script_upload||!strncmp(server.command.action,"script_",7)||!strcmp(server.command.action,"native")) dev_script_json(c,server.reply,sizeof(server.reply));
                else dev_status_json(c,server.reply,sizeof(server.reply));
            } else error_json(server.reply,sizeof(server.reply),error);
        }
        /* Publish the changed revision under the same lock as the acknowledgement.
         * A following status read must never precede an acknowledged command. */
        server.snapshot=*c;
        server.pending=2;
    }
    unlock();
}
void dev_server_publish(const DevCore *c) {
    if(server.mutex<0) return;
    lock(); server.snapshot=*c;
    if(server.pending==1&&server.operation==2) {
        vita2d_wait_rendering_done(); sceGxmDisplayQueueFinish();
        SceDisplayFrameBuf fb={0}; fb.size=sizeof(fb);
        int result=sceDisplayGetFrameBuf(&fb,SCE_DISPLAY_SETBUF_IMMEDIATE);
        if(result>=0&&fb.base&&fb.width==SCREEN_W&&fb.height==SCREEN_H&&fb.pitch>=SCREEN_W&&fb.pixelformat==SCE_DISPLAY_PIXELFORMAT_A8B8G8R8) {
            for(int y=0;y<SCREEN_H;y++) {
                unsigned char *row=server.pixels+(size_t)y*SCREEN_W*4;
                memcpy(row,(unsigned char*)fb.base+(size_t)y*fb.pitch*4,SCREEN_W*4);
                for(int x=0;x<SCREEN_W;x++) row[x*4+3]=255;
            }
            server.result=200; server.capture_revision=c->revision; server.capture_frame=c->frame; server.capture_ms=c->sampled_ms;
        } else { server.result=500; error_json(server.reply,sizeof(server.reply),"Own framebuffer unavailable"); }
        server.pending=2;
    }
    unlock();
}
void dev_server_address(char *out,size_t capacity) {
    SceNetCtlInfo info; int state=0;
    if(server.ctl&&sceNetCtlInetGetState(&state)>=0&&state==SCE_NETCTL_STATE_CONNECTED&&sceNetCtlInetGetInfo(SCE_NETCTL_INFO_GET_IP_ADDRESS,&info)>=0) snprintf(out,capacity,"%s:%d",info.ip_address,DEV_PORT);
    else snprintf(out,capacity,"Wi-Fi disconnected");
}
bool dev_server_paired(void) { return server.paired; }
void dev_server_stop(void) {
    if(server.mutex>=0) { lock(); server.running=false; unlock(); }
    if(server.thread>=0) { if(server.thread_started) sceKernelWaitThreadEnd(server.thread,NULL,NULL); sceKernelDeleteThread(server.thread); server.thread=-1; server.thread_started=false; }
    if(server.listener>=0) { sceNetSocketClose(server.listener); server.listener=-1; }
    if(server.ctl) { sceNetCtlTerm(); server.ctl=false; }
    if(server.net) { sceNetTerm(); server.net=false; }
    free(server.net_memory); server.net_memory=NULL;
    if(server.module) { sceSysmoduleUnloadModule(SCE_SYSMODULE_NET); server.module=false; }
    free(server.pixels); server.pixels=NULL;
    if(server.mutex>=0) { sceKernelDeleteMutex(server.mutex); server.mutex=-1; }
}
