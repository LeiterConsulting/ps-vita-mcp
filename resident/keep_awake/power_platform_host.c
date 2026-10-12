#define _POSIX_C_SOURCE 200809L
#include "power_platform.h"
#include "../platform.h"
#include "policy.h"
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static unsigned host_port=RKA_PORT;
static char host_root[1024];
static pthread_t power_thread;
static int worker_started;
static void (*power_worker)(void);
void rkap_host_config(unsigned port,const char *fixture_root) {
    host_port=port;R_SNPRINTF(host_root,sizeof(host_root),"%s",fixture_root);
}
static long long fixture_number(const char *name,long long fallback) {
    char path[1200],value[40]={0};R_SNPRINTF(path,sizeof(path),"%s/%s",host_root,name);
    int fd=open(path,O_RDONLY);if(fd<0) return fallback;
    int count=(int)read(fd,value,sizeof(value)-1);close(fd);
    return count>0?strtoll(value,0,10):fallback;
}
uint64_t rkap_now(void) {
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    uint64_t now=(uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
    long long offset=fixture_number("keep-awake-clock-offset",0);
    return offset<0&&(uint64_t)(-offset)>now?0:now+offset;
}
int rkap_host_network_ready(void) { return fixture_number("keep-awake-network",1)!=0; }
int rkap_tick(void) { return (int)fixture_number("keep-awake-tick-result",0); }
int rkap_listen(void) {
    int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0) return fd;
    int yes=1;setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
    struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_port=htons(host_port);
    address.sin_addr.s_addr=htonl(INADDR_ANY);
    if(bind(fd,(struct sockaddr *)&address,sizeof(address))<0||listen(fd,4)<0||
       fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK)<0) { close(fd);return -1; }
    return fd;
}
static void *worker_entry(void *arg) { (void)arg;power_worker();return 0; }
int rkap_worker_start(void (*worker)(void)) {
    if(worker_started) return -1;
    power_worker=worker;int result=pthread_create(&power_thread,0,worker_entry,0);
    if(!result) worker_started=1;
    return result?-1:0;
}
int rkap_worker_join(void) {
    if(!worker_started) return 0;
    int result=pthread_join(power_thread,0);
    if(!result) worker_started=0;
    return result?-1:0;
}
