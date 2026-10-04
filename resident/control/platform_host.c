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
    static char target[2048]; const char *prefix="ux0:data/vita-control";
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
int rc_host_base_main(int argc,char **argv) { if(argc!=4) return 2; snprintf(root,sizeof(root),"%s",argv[1]); port=(unsigned)strtoul(argv[2],0,10); signal(SIGTERM,stop); signal(SIGINT,stop); r_service(argv[3]); return 0; }

#include "control_platform.h"
#include "lease.h"
#include "pairing_privacy.h"
#include <dirent.h>
static RLease lease;
static int32_t foreground=77;
static uint32_t frame_sequence;
static int protected_process,unknown_process;
static int privacy_allowed(void) {char title[32]={0};snprintf(title,sizeof(title),"%s",protected_process?"CHRS00011":"CHRS00012");return rc_pairing_process_allowed(unknown_process?-1:0,title);}
static void refresh(void) { if(fault("starter")) protected_process=1;if(fault("title-fail")) unknown_process=1;if(fault("normal-title")) protected_process=unknown_process=0;if(fault("focus")) foreground=88; uint64_t now=r_now(); uint32_t reason=rlease_reason(&lease,now,foreground); if(reason) rlease_clear(&lease,now,reason); }
int rc_remove(const char *path) { return unlink(mapped(path)); }
int rc_list(const char *path,unsigned offset,RCEntry entries[32],int *more) {
    DIR *dir=opendir(mapped(path)); if(!dir) return -1; struct dirent *item; int count=0; unsigned skipped=0; *more=0;
    while((item=readdir(dir))) {
        if(!strcmp(item->d_name,".")||!strcmp(item->d_name,"..")) continue;
        if(skipped++<offset) continue;
        if(count==32) { *more=1; break; }
        if(strlen(item->d_name)>63) { closedir(dir); return -1; }
        char native[512]; snprintf(native,sizeof(native),"%s/%s",path,item->d_name); struct stat st;
        if(stat(mapped(native),&st)<0) { closedir(dir); return -1; }
        memcpy(entries[count].name,item->d_name,strlen(item->d_name)+1); entries[count].bytes=st.st_size; entries[count].directory=S_ISDIR(st.st_mode); count++;
    }
    closedir(dir); return count;
}
int rc_input(const RInput *input) { refresh(); if(!privacy_allowed()||!rlease_valid(input)||input->target_pid!=foreground) return -2; rlease_apply(&lease,input,r_now()); return 0; }
int rc_readback(RReadback *value) { refresh(); *value=(RReadback){0}; value->magic=RC_READ_MAGIC; value->abi=RC_ABI; value->sample_ms=r_now(); value->lease=lease; value->buttons=lease.input.buttons; value->sample_result=1; value->lx=value->ly=value->rx=value->ry=128; return 0; }
int rc_release(void) { rlease_clear(&lease,r_now(),RC_RELEASE_MANUAL); return 0; }
int rc_capture(unsigned char *pixels,RFrame *frame,unsigned scale) {
    refresh(); if(!privacy_allowed()||fault("capture")) return -3;
    *frame=(RFrame){0}; frame->magic=RC_FRAME_MAGIC; frame->abi=RC_ABI; frame->sequence=++frame_sequence;
    frame->width=960/scale; frame->height=544/scale; frame->bytes=frame->width*frame->height*3; frame->pid=foreground;
    frame->source_width=960; frame->source_height=544; frame->flags=1; frame->started_us=r_now()*1000; frame->ended_us=frame->started_us+100;
    for(unsigned i=0;i<frame->bytes;i++) pixels[i]=(unsigned char)(i%251);
    return 0;
}
int rc_app(int launch,const char *title) { (void)title; foreground=launch?77:88; rc_release(); return 0; }
int main(int argc,char **argv) { return rc_host_base_main(argc,argv); }
static RPState power_state;
static int brightness=50000;
int rp_start(void) { power_state.idle_ms=30000;power_state.dim_percent=20;return 0; }
int rp_stop(void) { return 0; }
int rp_set(const RPConfig *config) { if(!rp_valid(config)) return -1;rp_lease(&power_state,config,r_now());return 0; }
int rp_read(RPState *out) {
    RPAction action=rp_step(&power_state,r_now(),1,brightness,0,1);
    if(action.brightness>=21) { brightness=action.brightness;rp_applied(&power_state,brightness,0); }
    *out=power_state;return 0;
}
