#define _POSIX_C_SOURCE 200809L
#include "platform.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <netinet/in.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t active=1;
static unsigned port;
static char root[1024];
/* Test-only, one-shot faults; these adapters never enter the Vita binary. */
static int fault(const char *name) { char path[2048]; snprintf(path,sizeof(path),"%s/fault-%s",root,name); return unlink(path)==0; }
static const char *mapped(const char *path) {
    static char target[2048]; const char *prefix="ux0:data/vita-resident";
    if(strncmp(path,prefix,strlen(prefix))||strstr(path,"..")) return "/invalid-resident-path";
    snprintf(target,sizeof(target),"%s%s",root,path+strlen(prefix)); return target;
}
uint64_t r_now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000; }
void r_delay(unsigned ms) { struct timespec t={ms/1000,(long)(ms%1000)*1000000}; nanosleep(&t,0); }
int r_running(void) { return active; }
void r_log(const char *message,int result) { fprintf(stderr,"%s: %d\n",message,result); }
int r_network_init(void) { return 0; }
int r_network_ready(void) { return 1; }
void r_network_end(void) { }
static int nb(int fd) { return fcntl(fd,F_SETFL,fcntl(fd,F_GETFL)|O_NONBLOCK); }
static int again(void) { return errno==EAGAIN||errno==EWOULDBLOCK; }
int r_listen(void) { int fd=socket(AF_INET,SOCK_STREAM,0); if(fd<0) return fd; int yes=1; setsockopt(fd,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes)); struct sockaddr_in a={0}; a.sin_family=AF_INET; a.sin_port=htons(port); a.sin_addr.s_addr=htonl(INADDR_ANY); if(bind(fd,(struct sockaddr *)&a,sizeof(a))<0||listen(fd,2)<0||nb(fd)<0) { close(fd); return -1; } return fd; }
int r_accept(int fd) { int client=accept(fd,0,0); if(client<0) return again()?-1:-2; if(nb(client)<0) { close(client); return -1; } return client; }
int r_recv(int fd,void *data,size_t size) { int n=(int)recv(fd,data,size,0); return n<0&&again()?-2:n; }
int r_send(int fd,const void *data,size_t size) { int n=(int)send(fd,data,size,MSG_NOSIGNAL); return n<0&&again()?-2:n; }
void r_close_socket(int fd) { close(fd); }
void r_device(RDevice *d) { *d=(RDevice){73,0,333,222,111,111,3}; }
int r_dir(const char *path) { return mkdir(mapped(path),0700); }
int r_directory_exists(const char *path) { struct stat s; return stat(mapped(path),&s)==0&&S_ISDIR(s.st_mode); }
int r_open_write(const char *path) { return open(mapped(path),O_WRONLY|O_CREAT|O_EXCL,0600); }
int r_open_read(const char *path) { return open(mapped(path),O_RDONLY); }
int r_write(int fd,const void *data,size_t size) { if(fault("write")) return -1; if(fault("partial-write")&&size>1) size=1; return (int)write(fd,data,size); }
int r_read(int fd,void *data,size_t size) { if(fault("read")) return -1; int n=(int)read(fd,data,size); if(n>0&&fault("corrupt-read")) ((unsigned char *)data)[0]^=1; return n; }
int r_close_file(int fd) { int result=close(fd); return fault("close")?-1:result; }
int r_file_size(const char *path,uint64_t *size) { struct stat s; if(stat(mapped(path),&s)<0||!S_ISREG(s.st_mode)) return -1; *size=(uint64_t)s.st_size; return 0; }
int r_rename(const char *from,const char *to) { if(fault("rename")) return -1; char a[2048]; snprintf(a,sizeof(a),"%s",mapped(from)); const char *b=mapped(to); struct stat s; if(stat(b,&s)==0) return -1; return rename(a,b); }
static void stop(int signal_number) { (void)signal_number; active=0; }
int main(int argc,char **argv) { if(argc!=4) return 2; snprintf(root,sizeof(root),"%s",argv[1]); port=(unsigned)strtoul(argv[2],0,10); signal(SIGTERM,stop); signal(SIGINT,stop); r_service(argv[3]); return 0; }
