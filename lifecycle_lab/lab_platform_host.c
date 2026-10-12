/* Host-only POSIX sockets/thread adapter for the actual lab HTTP worker. */
#define _POSIX_C_SOURCE 200809L
#include "lab_platform.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_t thread;
static int (*work)(void);
static unsigned port;
static int listener=-1;
static const char *root;
void lp_host_config(const char *folder,unsigned value){root=folder;port=value;}
static int file(const char *name){char path[512];snprintf(path,sizeof(path),"%s/%s",root,name);return access(path,F_OK)==0;}
void lp_host_event(const char *value){char path[512];snprintf(path,sizeof(path),"%s/events.log",root);FILE *f=fopen(path,"a");if(f){fprintf(f,"%s\n",value);fclose(f);}}
uint64_t lp_now(void){struct timespec value;clock_gettime(CLOCK_MONOTONIC,&value);return (uint64_t)value.tv_sec*1000+(unsigned)value.tv_nsec/1000000;}
void lp_delay(unsigned ms){struct timespec delay={ms/1000,(long)(ms%1000)*1000000};nanosleep(&delay,0);}
int lp_pid(void){return (int)getpid();}
int lp_nonce(unsigned char nonce[16]){FILE *f=fopen("/dev/urandom","rb");if(!f)return 0;size_t n=fread(nonce,1,16,f);return fclose(f)==0&&n==16;}
int lp_init(void){return 0;}
void lp_end(void){}
void lp_lock(void){pthread_mutex_lock(&mutex);}
void lp_unlock(void){pthread_mutex_unlock(&mutex);}
int lp_token(char token[33]){
    char path[512];snprintf(path,sizeof(path),"%s/bridge.cfg",root);FILE *f=fopen(path,"rb");if(!f)return 0;
    char raw[35]={0};size_t n=fread(raw,1,sizeof(raw),f);int ok=fclose(f)==0;
    if(!ok||(n!=32&&!(n==33&&raw[32]=='\n')))return 0;
    for(unsigned i=0;i<32;i++)if(!((raw[i]>='0'&&raw[i]<='9')||(raw[i]>='a'&&raw[i]<='f')))return 0;
    memcpy(token,raw,32);token[32]=0;return 1;
}
static int nonblock(int socket){int flags=fcntl(socket,F_GETFL,0);return flags<0?-1:fcntl(socket,F_SETFL,flags|O_NONBLOCK);}
int lp_listen(void){
    int s=socket(AF_INET,SOCK_STREAM,0);if(s<0)return -1;int reuse=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&reuse,sizeof(reuse));
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons((uint16_t)port);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(s,(struct sockaddr *)&a,sizeof(a))<0||listen(s,2)<0||nonblock(s)<0){close(s);return -1;}listener=s;return s;
}
int lp_accept(int socket){int s=accept(socket,0,0);if(s>=0&&nonblock(s)<0){close(s);return -1;}return s;}
int lp_recv(int socket,void *data,size_t size){ssize_t n=recv(socket,data,size,0);return n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)?-2:(int)n;}
int lp_send(int socket,const void *data,size_t size){
    if(file("fault-send"))return -1;
    if(file("short-send")&&size>3)size=3;
    ssize_t n=send(socket,data,size,MSG_NOSIGNAL);
    if(n>0&&size>=22&&!memcmp(data,"{\"app\":\"Vita Native",19))lp_host_event("response-body");
    return n<0&&(errno==EAGAIN||errno==EWOULDBLOCK)?-2:(int)n;
}
int lp_close(int socket){int result=close(socket);lp_host_event(socket==listener?"listener-close":"socket-close");return file("fault-close")?-1:result;}
static void *entry(void *arg){(void)arg;work();return 0;}
int lp_thread_start(int (*worker)(void)){work=worker;return pthread_create(&thread,0,entry,0)==0?0:-1;}
int lp_thread_join(void){return pthread_join(thread,0)==0?0:-1;}
