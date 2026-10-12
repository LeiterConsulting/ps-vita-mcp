#include "files_platform.h"
#include <psp2/io/dirent.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>

static int valid_attempt(const char *attempt) {
    if(!attempt) return 0;
    for(unsigned i=0;i<32;i++)
        if(!((attempt[i]>='0'&&attempt[i]<='9')||(attempt[i]>='a'&&attempt[i]<='f'))) return 0;
    return !attempt[32];
}
static int valid_leaf(const char *leaf) {
    if(!leaf||!*leaf||!R_STRCMP(leaf,".")||!R_STRCMP(leaf,"..")) return 0;
    unsigned n=0;
    for(;leaf[n];n++) {
        char c=leaf[n];
        if(n>=63||!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-')) return 0;
    }
    return 1;
}
static int open_error(int result) { return result==(int)0x80010002u?-1:-2; }
static int directory_path(char path[160],const char *attempt) {
    if(attempt&&!valid_attempt(attempt)) return -1;
    int n=R_SNPRINTF(path,160,"ux0:data/vita-resident/inbox%s%s",attempt?"/":"",attempt?attempt:"");
    if(n<=0||n>=160) return -1;
    SceIoStat stat={0};
    int result=sceIoGetstat("ux0:data/vita-resident/inbox",&stat);
    if(result<0) return open_error(result);
    if(!SCE_S_ISDIR(stat.st_mode)) return -1;
    if(attempt) {
        result=sceIoGetstat(path,&stat);
        if(result<0) return open_error(result);
        if(!SCE_S_ISDIR(stat.st_mode)) return -1;
    }
    return 0;
}
int rf_dir_open(const char *attempt) {
    char path[160];
    int result=directory_path(path,attempt);
    if(result<0) return result;
    result=sceIoDopen(path);
    return result<0?open_error(result):result;
}
int rf_dir_next(int handle,RFEntry *entry) {
    if(!entry) return -1;
    SceIoDirent next;
    unsigned n;
    for(;;) {
        R_MEMSET(&next,0,sizeof(next));
        int result=sceIoDread(handle,&next);
        if(result<=0) return result<0?-1:0;
        n=0;
        while(n<sizeof(next.d_name)&&next.d_name[n]) n++;
        if(n>=sizeof(next.d_name)) return -1;
        if(R_STRCMP(next.d_name,".")&&R_STRCMP(next.d_name,"..")) break;
    }
    R_MEMSET(entry,0,sizeof(*entry));
    R_MEMCPY(entry->name,next.d_name,n+1);
    entry->kind=SCE_S_ISREG(next.d_stat.st_mode)?1:SCE_S_ISDIR(next.d_stat.st_mode)?2:0;
    entry->bytes=next.d_stat.st_size>=0?(uint64_t)next.d_stat.st_size:0;
    return 1;
}
int rf_dir_close(int handle) { return sceIoDclose(handle)<0?-1:0; }
int rf_size(int fd,uint64_t *size) {
    SceIoStat stat={0};
    if(!size) return -1;
    if(sceIoGetstatByFd(fd,&stat)<0) return -2;
    if(!SCE_S_ISREG(stat.st_mode)||stat.st_size<0||(uint64_t)stat.st_size>R_MAX_FILE) return -1;
    *size=(uint64_t)stat.st_size;
    return 0;
}
int rf_open(const char *attempt,const char *leaf,uint64_t *size) {
    char directory[160],path[256];
    if(!valid_attempt(attempt)||!valid_leaf(leaf)||!size) return -1;
    int result=directory_path(directory,attempt);
    if(result<0) return result;
    int n=R_SNPRINTF(path,sizeof(path),"%s/%s",directory,leaf);
    if(n<=0||(unsigned)n>=sizeof(path)) return -1;
    SceIoStat stat={0};
    result=sceIoGetstat(path,&stat);
    if(result<0) return open_error(result);
    if(!SCE_S_ISREG(stat.st_mode)||stat.st_size<0||(uint64_t)stat.st_size>R_MAX_FILE) return -1;
    int fd=sceIoOpen(path,SCE_O_RDONLY|SCE_O_NBLOCK,0);
    if(fd<0) return open_error(fd);
    result=rf_size(fd,size);
    if(result<0) { sceIoClose(fd); return result; }
    return fd;
}
int rf_seek(int fd,uint64_t offset) {
    if(offset>R_MAX_FILE) return -1;
    SceOff result=sceIoLseek(fd,(SceOff)offset,SCE_SEEK_SET);
    return result>=0&&(uint64_t)result==offset?0:-1;
}
int rf_close(int fd) { return sceIoClose(fd)<0?-1:0; }
