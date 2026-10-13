#include "lab_server.h"
#include "lab_platform.h"
#include <stdio.h>
#include <string.h>
#include <strings.h>

static struct {
    int listener,running,started,pending,result,complete;
    char token[33],body[512],reply[LAB_JSON_MAX];
    size_t body_bytes;
    LabCore snapshot;
} server;
static int running(void){lp_lock();int value=server.running;lp_unlock();return value;}
static int send_all(int socket,const void *data,size_t size,uint64_t deadline) {
    const unsigned char *p=data;
    while(size&&running()&&lp_now()<deadline){int n=lp_send(socket,p,size);
        if(n>0&&(size_t)n<=size){p+=n;size-=(unsigned)n;}
        else if(n==-2)lp_delay(1);else return 0;}
    return !size;
}
static int response(int socket,int status,const char *body) {
    char header[256];size_t bytes=strlen(body);
    int n=snprintf(header,sizeof(header),"HTTP/1.1 %d Result\r\nContent-Type: application/json\r\nContent-Length: %u\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",status,(unsigned)bytes);
    uint64_t end=lp_now()+4000;
    return n>0&&(size_t)n<sizeof(header)&&send_all(socket,header,(size_t)n,end)&&send_all(socket,body,bytes,end);
}
static void failure(int socket,int status){response(socket,status,"{\"error\":\"Lifecycle lab request refused\"}");}
static int authorized(const char *value) {
    if(strlen(value)!=39||memcmp(value,"Bearer ",7))return 0;
    unsigned difference=0;for(unsigned n=0;n<32;n++)difference|=(unsigned char)value[n+7]^(unsigned char)server.token[n];
    return difference==0;
}
static int request(int socket,char method[8],char path[64],char body[512],size_t *size) {
    char raw[4097];size_t used=0;char *end=0;uint64_t deadline=lp_now()+2500;
    while(!end&&used<sizeof(raw)-1&&running()&&lp_now()<deadline){
        int n=lp_recv(socket,raw+used,sizeof(raw)-1-used);
        if(n>0){used+=(unsigned)n;raw[used]=0;end=strstr(raw,"\r\n\r\n");}
        else if(n==-2)lp_delay(1);else return 400;
    }
    if(!end)return 400;
    size_t header_size=(size_t)(end-raw)+4;
    if(memchr(raw,0,header_size))return 400;
    *end=0;char *first=strstr(raw,"\r\n");if(!first)return 400;*first=0;
    char version[16],extra;
    if(sscanf(raw,"%7s %63s %15s %c",method,path,version,&extra)!=3||strcmp(version,"HTTP/1.1"))return 400;
    int auth=0,length_seen=0,type_seen=0;size_t length=0;
    for(char *line=first+2;*line;){
        if(*line==' '||*line=='\t')return 400;
        char *next=strstr(line,"\r\n");if(next)*next=0;
        char *colon=strchr(line,':');if(!colon)return 400;*colon++=0;while(*colon==' '||*colon=='\t')colon++;
        if(!strcasecmp(line,"Authorization")){if(auth||!authorized(colon))return 401;auth=1;}
        else if(!strcasecmp(line,"Content-Length")){
            if(length_seen++||!*colon||strlen(colon)>3)return 400;
            for(const char *p=colon;*p;p++){if(*p<'0'||*p>'9')return 400;length=length*10+(unsigned)(*p-'0');}
            if(length>511)return 413;
        }else if(!strcasecmp(line,"Content-Type")){if(type_seen++||strcmp(colon,"application/json"))return 415;}
        else if(!strcasecmp(line,"Transfer-Encoding")||!strcasecmp(line,"Expect"))return 400;
        if(!next)break;
        line=next+2;
    }
    if(!auth)return 401;
    if(strcmp(method,"GET")&&strcmp(method,"POST"))return 405;
    if(!strcmp(method,"GET")&&length)return 400;
    if(!strcmp(method,"POST")&&(!length_seen||!length||!type_seen))return 400;
    if(used>header_size+length)return 400;
    size_t have=used-header_size;memcpy(body,raw+header_size,have);
    while(have<length&&running()&&lp_now()<deadline){int n=lp_recv(socket,body+have,length-have);
        if(n>0)have+=(unsigned)n;else if(n==-2)lp_delay(1);else return 400;}
    if(have!=length||memchr(body,0,length))return 400;
    body[length]=0;*size=length;return 200;
}
/* Returns whether one accepted exit needs its post-socket-close decision. */
static int handle(int socket,int *complete) {
    char method[8],path[64],body[512],json[LAB_JSON_MAX];size_t size=0;*complete=0;
    int code=request(socket,method,path,body,&size);
    if(code!=200){failure(socket,code);return 0;}
    lp_lock();LabCore snapshot=server.snapshot;lp_unlock();
    uint64_t now=lp_now();
    if(!snapshot.frame||now<snapshot.sampled_ms||now-snapshot.sampled_ms>=1500){failure(socket,503);return 0;}
    if(!strcmp(method,"GET")&&!strcmp(path,"/status")){
        if(lab_status(&snapshot,json,sizeof(json),0)<0){failure(socket,503);return 0;}
        response(socket,200,json);return 0;
    }
    if(strcmp(method,"POST")||strcmp(path,"/exit")){failure(socket,404);return 0;}
    lp_lock();memcpy(server.body,body,size+1);server.body_bytes=size;server.pending=1;lp_unlock();
    uint64_t deadline=lp_now()+1200;int done=0;
    while(running()&&lp_now()<deadline){lp_lock();done=server.pending==2;lp_unlock();if(done)break;lp_delay(1);}
    lp_lock();
    if(server.pending==2){done=1;code=server.result;snprintf(json,sizeof(json),"%s",server.reply);}
    else{done=0;server.pending=0;}
    lp_unlock();
    if(!done){failure(socket,503);return 0;}
    *complete=response(socket,code,json);
    if(code!=200){lp_lock();server.pending=0;lp_unlock();return 0;}
    return 1;
}
static int worker(void) {
    while(running()){
        int socket=lp_accept(server.listener);if(socket<0){lp_delay(5);continue;}
        int complete=0,exit_accepted=handle(socket,&complete);
        int closed=lp_close(socket);
        if(exit_accepted){lp_lock();server.complete=complete&&closed==0;server.pending=3;lp_unlock();}
    }
    return 0;
}
int lab_server_start(const LabCore *core) {
    memset(&server,0,sizeof(server));server.listener=-1;
    if(lp_init()<0)return -1;
    if(!lp_token(server.token)){lp_end();return -1;}
    server.snapshot=*core;server.listener=lp_listen();
    if(server.listener<0){lp_end();return -1;}
    server.running=1;
    if(lp_thread_start(worker)<0){server.running=0;lp_close(server.listener);lp_end();return -1;}
    server.started=1;return 0;
}
void lab_server_tick(LabCore *core) {
    if(!server.started)return;
    lp_lock();
    if(server.pending==1){
        server.result=lab_offer_exit(core,server.body,server.body_bytes);
        if(server.result==200)lab_status(core,server.reply,sizeof(server.reply),1);
        else snprintf(server.reply,sizeof(server.reply),"{\"error\":\"Exit pins or state refused\"}");
        server.pending=2;
    }else if(server.pending==3){lab_finish_exit(core,server.complete,server.complete);server.pending=0;}
    server.snapshot=*core;
    lp_unlock();
}
int lab_server_stop(void) {
    if(!server.started)return 0;
    lp_lock();server.running=0;lp_unlock();
    int result=lp_thread_join();
    if(result<0)return result;
    lp_close(server.listener);server.listener=-1;server.started=0;
    memset(server.token,0,sizeof(server.token));lp_end();return 0;
}
