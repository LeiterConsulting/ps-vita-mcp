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
static uint64_t after_apply_offset;
void rkap_host_config(unsigned port,const char *fixture_root) {
    host_port=port;R_SNPRINTF(host_root,sizeof(host_root),"%s",fixture_root);
    after_apply_offset=0;
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
    now+=after_apply_offset;
    return offset<0&&(uint64_t)(-offset)>now?0:now+offset;
}
int rkap_host_network_ready(void) { return fixture_number("keep-awake-network",1)!=0; }
int rkap_tick(void) { return (int)fixture_number("keep-awake-tick-result",0); }
/* These file seams exist only in the host fixture, never in the Vita artifact. */
static int consume_number(const char *name,long long *value) {
    char path[1200],text[40]={0};R_SNPRINTF(path,sizeof(path),"%s/%s",host_root,name);
    int fd=open(path,O_RDONLY);if(fd<0) return 0;
    int count=(int)read(fd,text,sizeof(text)-1);close(fd);unlink(path);
    *value=count>0?strtoll(text,0,10):0;return 1;
}
void rkap_host_after_apply(void) {
    long long value=0;if(consume_number("keep-awake-after-apply-clock-advance",&value)&&value>0&&value<=10000) after_apply_offset+=(uint64_t)value;
}
RKANetworkResult rkap_network(void) {
    RKANetworkResult result;
    result.result=(int)fixture_number("keep-awake-network-result",0);
    result.state=(int)fixture_number("keep-awake-network-state",r_network_ready()&&rkap_host_network_ready()?3:0);
    return result;
}
static void captured(RKASocketResult *out,int stage,int raw,int error) { out->result=raw;out->error=raw<0?error:0;out->stage=stage; }
static int forced(const char *name,RKASocketResult *out,int stage) {
    long long value;
    if(!consume_number(name,&value)) return 0;
    captured(out,stage,-1,value>0&&value<=INT32_MAX?(int)value:EIO);return 1;
}
static int would_block(const RKASocketResult *out) { return out->error==EAGAIN||out->error==EWOULDBLOCK; }
static void cleanup(int fd,RKASocketResult *out) { int raw=close(fd),error=raw<0?errno:0;out->close_result=raw;out->close_error=error; }
int rkap_close(int fd,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));int raw=close(fd),error=raw<0?errno:0;captured(out,RKA_STAGE_CLOSE,raw,error);
    if(forced("keep-awake-fault-close",out,RKA_STAGE_CLOSE)) return -1;
    return raw;
}
int rkap_accept(int fd,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));
    if(forced("keep-awake-fault-accept",out,RKA_STAGE_ACCEPT)) return would_block(out)?-1:-2;
    int client=accept(fd,0,0),error=client<0?errno:0;captured(out,RKA_STAGE_ACCEPT,client,error);
    if(client<0) return would_block(out)?-1:-2;
    if(forced("keep-awake-fault-client-nbio",out,RKA_STAGE_CLIENT_NBIO)) { cleanup(client,out);return -1; }
    int raw=fcntl(client,F_SETFL,fcntl(client,F_GETFL)|O_NONBLOCK);error=raw<0?errno:0;
    if(raw<0) { captured(out,RKA_STAGE_CLIENT_NBIO,raw,error);cleanup(client,out);return -1; }
    return client;
}
int rkap_recv(int fd,void *data,size_t size,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));
    if(forced("keep-awake-fault-recv",out,RKA_STAGE_RECV)) return would_block(out)?-2:-1;
    long long value;if(consume_number("keep-awake-fault-recv-eof",&value)) { captured(out,RKA_STAGE_RECV,0,0);return 0; }
    int raw=(int)recv(fd,data,size,0),error=raw<0?errno:0;captured(out,RKA_STAGE_RECV,raw,error);return raw<0&&would_block(out)?-2:raw;
}
int rkap_send(int fd,const void *data,size_t size,RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));
    if(forced("keep-awake-fault-send",out,RKA_STAGE_SEND)) return would_block(out)?-2:-1;
    if(fixture_number("keep-awake-send-would-block",0)>0) { captured(out,RKA_STAGE_SEND,-1,EAGAIN);return -2; }
    long long limit=fixture_number("keep-awake-send-limit",0);if(limit>0&&(uint64_t)limit<size) size=(size_t)limit;
    int raw=(int)send(fd,data,size,MSG_NOSIGNAL),error=raw<0?errno:0;captured(out,RKA_STAGE_SEND,raw,error);return raw<0&&would_block(out)?-2:raw;
}
int rkap_listen(RKASocketResult *out) {
    R_MEMSET(out,0,sizeof(*out));
    if(forced("keep-awake-fault-listen-create",out,RKA_STAGE_SOCKET)) return -1;
    int fd=socket(AF_INET,SOCK_STREAM,0),error=fd<0?errno:0;captured(out,RKA_STAGE_SOCKET,fd,error);if(fd<0) return fd;
    int yes=1;RKASocketResult reuse={0};
    if(!forced("keep-awake-fault-listen-reuse",&reuse,RKA_STAGE_REUSE)) { int raw=setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));error=raw<0?errno:0;captured(&reuse,RKA_STAGE_REUSE,raw,error); }
    struct sockaddr_in address={0};address.sin_family=AF_INET;address.sin_port=htons(host_port);
    address.sin_addr.s_addr=htonl(INADDR_ANY);
    if(forced("keep-awake-fault-listen-bind",out,RKA_STAGE_BIND)) { cleanup(fd,out);return -1; }
    int raw=bind(fd,(struct sockaddr *)&address,sizeof(address));error=raw<0?errno:0;captured(out,RKA_STAGE_BIND,raw,error);
    if(raw<0) { cleanup(fd,out);return -1; }
    if(forced("keep-awake-fault-listen-listen",out,RKA_STAGE_LISTEN)) { cleanup(fd,out);return -1; }
    raw=listen(fd,4);error=raw<0?errno:0;captured(out,RKA_STAGE_LISTEN,raw,error);
    if(raw<0) { cleanup(fd,out);return -1; }
    if(forced("keep-awake-fault-listener-nbio",out,RKA_STAGE_LISTENER_NBIO)) { cleanup(fd,out);return -1; }
    raw=fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK);error=raw<0?errno:0;captured(out,RKA_STAGE_LISTENER_NBIO,raw,error);
    if(raw<0) { cleanup(fd,out);return -1; }
    if(reuse.result<0) *out=reuse;
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
