#define _POSIX_C_SOURCE 200809L
#include "files_platform.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static char fixture_root[1024];
static DIR *directory;

void rf_host_root(const char *root) {
    size_t n=root?strlen(root):0;
    fixture_root[0]=0;
    if(n&&n<sizeof(fixture_root)) memcpy(fixture_root,root,n+1);
}
/* Test-only faults never enter the native adapter. */
static int fault(const char *name) {
    char path[1200];
    int n=snprintf(path,sizeof(path),"%s/fault-%s",fixture_root,name);
    return n>0&&(size_t)n<sizeof(path)&&unlink(path)==0;
}
static int valid_attempt(const char *attempt) {
    if(!attempt) return 0;
    for(unsigned i=0;i<32;i++)
        if(!((attempt[i]>='0'&&attempt[i]<='9')||(attempt[i]>='a'&&attempt[i]<='f'))) return 0;
    return !attempt[32];
}
static int valid_leaf(const char *leaf) {
    if(!leaf||!*leaf||!strcmp(leaf,".")||!strcmp(leaf,"..")) return 0;
    unsigned n=0;
    for(;leaf[n];n++) {
        char c=leaf[n];
        if(n>=63||!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-')) return 0;
    }
    return 1;
}
static int open_error(void) { return errno==ENOENT||errno==ENOTDIR||errno==ELOOP?-1:-2; }
/* Pin every untrusted path component. An open file remains pinned even if an
   external process renames its parent or replaces its pathname afterward. */
static int managed_directory(const char *attempt) {
    if(!fixture_root[0]||(attempt&&!valid_attempt(attempt))) return -1;
    int root=open(fixture_root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(root<0) return open_error();
    int inbox=openat(root,"inbox",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    int failed=inbox<0?open_error():0;
    int closed=close(root);
    if(inbox<0) return failed;
    if(closed<0) { close(inbox); return -2; }
    if(!attempt) return inbox;
    int fd=openat(inbox,attempt,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    failed=fd<0?open_error():0;
    closed=close(inbox);
    if(fd>=0&&closed<0) { close(fd); return -2; }
    return fd<0?failed:fd;
}
int rf_dir_open(const char *attempt) {
    if(directory||fault("files-directory")) return -2;
    int fd=managed_directory(attempt);
    if(fd<0) return fd;
    directory=fdopendir(fd);
    if(!directory) { close(fd); return -2; }
    return 1;
}
int rf_dir_next(int handle,RFEntry *entry) {
    if(handle!=1||!directory||!entry||fault("files-dir-read")) return -1;
    struct dirent *next;
    do {
        errno=0;
        next=readdir(directory);
        if(!next) return errno?-1:0;
    } while(!strcmp(next->d_name,".")||!strcmp(next->d_name,".."));
    size_t n=strlen(next->d_name);
    if(n>=sizeof(entry->name)) return -1;
    memset(entry,0,sizeof(*entry));
    memcpy(entry->name,next->d_name,n+1);
    struct stat stat;
    if(fault("files-stat")||fstatat(dirfd(directory),next->d_name,&stat,AT_SYMLINK_NOFOLLOW)<0) return -1;
    entry->kind=S_ISREG(stat.st_mode)?1:S_ISDIR(stat.st_mode)?2:0;
    entry->bytes=stat.st_size>=0?(uint64_t)stat.st_size:0;
    return 1;
}
int rf_dir_close(int handle) {
    if(handle!=1||!directory) return -1;
    DIR *opened=directory;
    directory=NULL;
    int result=closedir(opened);
    return fault("files-dir-close")?-1:result;
}
int rf_size(int fd,uint64_t *size) {
    struct stat stat;
    if(!size) return -1;
    if(fault("files-stat")||fstat(fd,&stat)<0) return -2;
    if(!S_ISREG(stat.st_mode)||stat.st_size<0||(uint64_t)stat.st_size>R_MAX_FILE) return -1;
    *size=(uint64_t)stat.st_size;
    if(fault("files-size-change")) (*size)++;
    return 0;
}
int rf_open(const char *attempt,const char *leaf,uint64_t *size) {
    if(!valid_attempt(attempt)||!valid_leaf(leaf)||!size) return -1;
    if(fault("files-open")) return -2;
    if(fault("files-deadline")) r_delay(11000);
    int parent=managed_directory(attempt);
    if(parent<0) return parent;
    /* Nonblocking avoids waiting on a FIFO before fstat rejects its kind. */
    int fd=openat(parent,leaf,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
    int failed=fd<0?open_error():0;
    int closed=close(parent);
    if(fd<0) return failed;
    if(closed<0) { close(fd); return -2; }
    failed=rf_size(fd,size);
    if(failed<0) { close(fd); return failed; }
    return fd;
}
int rf_seek(int fd,uint64_t offset) {
    if(offset>R_MAX_FILE||fault("files-seek")) return -1;
    off_t result=lseek(fd,(off_t)offset,SEEK_SET);
    return result>=0&&(uint64_t)result==offset?0:-1;
}
int rf_close(int fd) {
    int result=close(fd);
    return fault("files-close")?-1:result;
}
