#define _POSIX_C_SOURCE 200809L
/* Standalone real-C HTTP fixture. No host adapter enters the Vita build. */
#include "../platform.h"
#include "service.h"
#include "power_platform.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t active=1;
static int again(void) { return errno==EAGAIN||errno==EWOULDBLOCK; }
int r_running(void) { return active; }
int r_network_ready(void) { return 1; }
void r_delay(unsigned ms) { struct timespec delay={ms/1000,(long)(ms%1000)*1000000};nanosleep(&delay,0); }
int r_pair_random(void *out,size_t bytes) { int fd=open("/dev/urandom",O_RDONLY);if(fd<0) return -1;int n=(int)read(fd,out,bytes);close(fd);return n==(int)bytes?0:-1; }
int r_accept(int fd) { int client=accept(fd,0,0);if(client<0) return again()?-1:-2;if(fcntl(client,F_SETFL,fcntl(client,F_GETFL)|O_NONBLOCK)<0) { close(client);return -1; }return client; }
int r_recv(int fd,void *data,size_t size) { int n=(int)recv(fd,data,size,0);return n<0&&again()?-2:n; }
int r_send(int fd,const void *data,size_t size) { int n=(int)send(fd,data,size,MSG_NOSIGNAL);return n<0&&again()?-2:n; }
void r_close_socket(int fd) { close(fd); }
static void stop(int number) { (void)number;active=0; }
int main(int argc,char **argv) {
    if(argc!=4) return 2;
    rkap_host_config((unsigned)strtoul(argv[2],0,10),argv[1]);signal(SIGTERM,stop);signal(SIGINT,stop);
    if(rka_start(argv[3])<0) return 3;
    while(active) r_delay(20);
    return rka_stop()<0?4:0;
}
