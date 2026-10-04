#define _POSIX_C_SOURCE 200809L
#include "pairing_client.h"
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static uint64_t mono(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;}
static void delay(unsigned ms){struct timespec t={ms/1000,(long)(ms%1000)*1000000};nanosleep(&t,0);}
static int again(void){return errno==EAGAIN||errno==EWOULDBLOCK;}
static int connect_local(unsigned port) {
    /* Test-only alternate port; never compiled into the Vita. */
    const char *p=getenv("PR_RESIDENT_PORT");if(p)port=(unsigned)strtoul(p,0,10);
    int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return -1;
    struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_port=htons((uint16_t)port);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    /* A loopback TCP connect cannot wait on a remote network. */
    if(connect(fd,(struct sockaddr *)&a,sizeof(a))<0||fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK)<0){close(fd);return -1;}return fd;
}
static int send_local(int fd,const void *data,size_t n){int r=(int)send(fd,data,n,MSG_NOSIGNAL);return r<0&&again()?-2:r;}
static int recv_local(int fd,void *data,size_t n){int r=(int)recv(fd,data,n,0);return r<0&&again()?-2:r;}
static void close_local(int fd){close(fd);}
const PCIO *pc_platform_io(void){static const PCIO io={mono,delay,connect_local,send_local,recv_local,close_local};return &io;}
