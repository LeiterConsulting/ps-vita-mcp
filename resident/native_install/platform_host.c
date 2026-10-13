#define _POSIX_C_SOURCE 200809L
#include "platform.h"
#include "service.h"
#include "../platform.h"
#include "../native_launch/native_launch.h"
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <errno.h>
#include <stdlib.h>

extern const char *const ni_file_names[NI_FILE_COUNT];
static char host_root[1024],scope[1200];
static unsigned submissions;
static int promoting,promote_polls;
static char promoting_path[192];
static char direct_fault[64];static int direct_value;
static int fault(const char *name) {
    if(!strcmp(direct_fault,name)&&direct_value){int value=direct_value;
        direct_value=0;
        return value;
        }
    char p[1200];
    snprintf(p,sizeof(p),"%s/native-fault-%s",host_root,name);
    return unlink(p)==0;
}
void nip_host_fault(const char *name,int value) {snprintf(direct_fault,sizeof(direct_fault),"%s",name);
    direct_value=value;
    }
unsigned nip_host_submissions(void) {return submissions;
    }
void nip_host_root(const char *root) {snprintf(host_root,sizeof(host_root),"%s",root);
    snprintf(scope,sizeof(scope),"%s/n1/%s",host_root,R_BUILD_ID);
    promoting=0;
    promote_polls=0;
    promoting_path[0]=0;
    direct_fault[0]=0;
    direct_value=0;
    }
static int components(const char *s) {
    if(!s||!*s||*s=='/'||strstr(s,"..")||strchr(s,'\\')||strchr(s,':'))return 0;
    for(size_t n=0;s[n];n++)if(!((s[n]>='a'&&s[n]<='z')||(s[n]>='A'&&s[n]<='Z')||(s[n]>='0'&&s[n]<='9')||s[n]=='/'||s[n]=='_'||s[n]=='-'||s[n]=='.'))return 0;
    return 1;
}
/* Walk every parent with O_NOFOLLOW; a host symlink cannot redirect a managed
   write, record read, promotion source, or installed observation. */
static int parent_at(const char *relative,char leaf[128],int installed) {
    if(!components(relative))return -1;
    const char *base=installed?host_root:scope;
    int fd=open(base,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(fd<0)return -1;
    char copy[256];
    if(strlen(relative)>=sizeof(copy)){close(fd);
        return -1;
        }strcpy(copy,relative);
    char *at=copy,*slash;
    while((slash=strchr(at,'/'))!=NULL) {
        *slash=0;
        if(!*at){close(fd);
            return -1;
            }
        int next=openat(fd,at,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
        close(fd);
        if(next<0)return -1;
        fd=next;
        at=slash+1;
    }
    if(!*at||strlen(at)>=128){close(fd);
        return -1;
        }strcpy(leaf,at);
    return fd;
}
static int safe_mkdir_absolute(const char *p) {
    if(mkdir(p,0700)==0)return 0;
    struct stat st;
    if(errno!=EEXIST||lstat(p,&st)||!S_ISDIR(st.st_mode))return -1;
    return 0;
}
int nip_init(void) {
    if(!host_root[0])return -1;
    char base[1200];
    snprintf(base,sizeof(base),"%s/n1",host_root);
    return safe_mkdir_absolute(base)||safe_mkdir_absolute(scope)?-1:0;
}
int nip_kind(const char *relative,uint64_t *bytes) {
    char clean[256];
    size_t n=strlen(relative);
    if(n>=sizeof(clean))return -1;
    strcpy(clean,relative);
    if(n&&clean[n-1]=='/')clean[n-1]=0;
    char leaf[128];
    int parent=parent_at(clean,leaf,0);
    if(parent<0)return -1;
    struct stat st;
    int r=fstatat(parent,leaf,&st,AT_SYMLINK_NOFOLLOW),error=errno;
    close(parent);
    if(r<0)return error==ENOENT?0:-1;
    if(st.st_size<0)return -1;
    if(bytes)*bytes=(uint64_t)st.st_size;
    return S_ISREG(st.st_mode)?1:S_ISDIR(st.st_mode)?2:-1;
}
int nip_mkdir(const char *relative) {
    char clean[256];
    size_t n=strlen(relative);
    if(n>=sizeof(clean))return -1;
    strcpy(clean,relative);
    if(n&&clean[n-1]=='/')clean[n-1]=0;
    char leaf[128];
    int parent=parent_at(clean,leaf,0);
    if(parent<0)return -1;
    int r=mkdirat(parent,leaf,0700),error=errno;
    close(parent);
    if(!r)return 0;
    return error==EEXIST&&nip_kind(clean,0)==2?1:-1;
}
int nip_open_read(const char *relative) {
    if(fault("open-read"))return -1;
    char leaf[128];
    int parent=parent_at(relative,leaf,0);
    if(parent<0)return -1;
    int fd=openat(parent,leaf,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    close(parent);
    uint64_t bytes;
    if(fd>=0&&nip_size(fd,&bytes)){close(fd);
        return -1;
        }return fd;
}
int nip_open_new(const char *relative) {
    if(fault("open-new"))return -1;
    char leaf[128];
    int parent=parent_at(relative,leaf,0);
    if(parent<0)return -1;
    int fd=openat(parent,leaf,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
    close(parent);
    return fd;
}
int nip_read(int fd,void *out,size_t n) {if(fault("read"))return -1;
    if(fault("short-read")&&n>1)n=1;
    return (int)read(fd,out,n);
    }
int nip_write(int fd,const void *data,size_t n) {if(fault("write"))return -1;
    if(fault("short-write")&&n>1)n=1;
    return (int)write(fd,data,n);
    }
int nip_size(int fd,uint64_t *bytes) {struct stat st;
    if(fault("stat")||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<0)return -1;
    *bytes=(uint64_t)st.st_size;
    return 0;
    }
int nip_sync(int fd) {return fault("sync")?-1:fsync(fd);
    }
int nip_close(int fd) {int r=close(fd);
    return fault("close")?-1:r;
    }
int nip_sync_device(void) {if(fault("device-sync"))return -1;
    int fd=open(scope,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    if(fd<0)return -1;
    int r=fsync(fd);
    if(close(fd))r=-1;
    return r;
    }
int nip_rename_new(const char *from,const char *to) {
    if(fault("rename"))return -1;
    char a[128],b[128];
    int left=parent_at(from,a,0),right=parent_at(to,b,0);
    if(left<0||right<0){if(left>=0)close(left);
        if(right>=0)close(right);
        return -1;
        }
    /* linkat is atomic no-replace publication for host regular files. */
    int r=linkat(left,a,right,b,0);
    if(!r)r=unlinkat(left,a,0);
    close(left);
    close(right);
    return r;
}
int nip_list(const char *relative,unsigned index,char out[64]) {
    if(fault("list"))return -1;
    char leaf[128];
    int parent=parent_at(relative,leaf,0);
    if(parent<0)return -1;
    int fd=openat(parent,leaf,O_RDONLY|O_DIRECTORY|O_NOFOLLOW);
    close(parent);
    if(fd<0)return -1;
    DIR *dir=fdopendir(fd);
    if(!dir){close(fd);
        return -1;
        }
    unsigned seen=0;
    int result=0;
    struct dirent *entry;
    errno=0;
    while((entry=readdir(dir))) {
        if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
        if(seen++!=index)continue;
        if(strlen(entry->d_name)>=64)result=-1;
        else {strcpy(out,entry->d_name);
            result=1;
            }break;
    }
    if(!entry&&errno)result=-1;
    if(closedir(dir))result=-1;
    return result;
}
int nip_free(uint64_t *bytes) {if(fault("space"))return -1;
    struct statvfs st;
    if(statvfs(scope,&st))return -1;
    *bytes=(uint64_t)st.f_bavail*st.f_frsize;
    return 0;
    }
int nip_installed_kind(void) {
    char p[1200];
    snprintf(p,sizeof(p),"%s/native-installed/" NI_TITLE,host_root);
    struct stat st;
    if(lstat(p,&st))return errno==ENOENT?0:-1;
    return S_ISDIR(st.st_mode)?2:-1;
}
int nip_installed_open(unsigned index) {
    if(index>=NI_FILE_COUNT)return -1;
    char relative[192];
    snprintf(relative,sizeof(relative),"native-installed/" NI_TITLE "/%s",ni_file_names[index]);
    char leaf[128];
    int parent=parent_at(relative,leaf,1);
    if(parent<0)return -1;
    int fd=openat(parent,leaf,O_RDONLY|O_NOFOLLOW|O_NONBLOCK);
    close(parent);
    return fd;
}
static int install_copy(void) {
    const char *dirs[]={"native-installed","native-installed/" NI_TITLE,"native-installed/" NI_TITLE "/sce_sys","native-installed/" NI_TITLE "/sce_sys/livearea","native-installed/" NI_TITLE "/sce_sys/livearea/contents","native-installed/" NI_TITLE "/sce_sys/package"};
    for(unsigned i=0;i<6;i++){char p[1200];
        snprintf(p,sizeof(p),"%s/%s",host_root,dirs[i]);
        if(safe_mkdir_absolute(p))return -1;
        }
    for(unsigned i=0;i<NI_FILE_COUNT;i++) {
        char source[256],relative[192],leaf[128];
        snprintf(source,sizeof(source),"%s/%s",promoting_path,ni_file_names[i]);
        int in=nip_open_read(source);
        snprintf(relative,sizeof(relative),"native-installed/" NI_TITLE "/%s",ni_file_names[i]);
        int parent=parent_at(relative,leaf,1);
        if(in<0||parent<0){if(in>=0)close(in);
            if(parent>=0)close(parent);
            return -1;
            }
        int out=openat(parent,leaf,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW,0600);
        close(parent);
        if(out<0){close(in);
            return -1;
            }
        unsigned char data[8192];
        int n,good=1;
        while((n=(int)read(in,data,sizeof(data)))>0)if(write(out,data,(size_t)n)!=n){good=0;
            break;
            }
        if(n<0)good=0;
        if(close(in)||close(out))good=0;
        if(!good)return -1;
    }
    return 0;
}
int nip_promote_available(int *paf_result,int *promoter_result) {
    *paf_result=0;
    *promoter_result=promoting?0:(int)0x805a1001u;
    return !promoting;
}
int nip_promote_start(const char *relative,uint64_t issued,uint64_t expires,int *invoked,int *cleanup_result) {
    *invoked=0;
    *cleanup_result=0;
    if(promoting||fault("promoter-busy"))return -13002;
    if(fault("paf"))return -13001;
    if(fault("promoter-init"))return -13003;
    uint64_t now=r_pair_mono();
    int policy=nl_idle_policy(NI_TITLE,1);
    if(issued>now||now-issued>5000||now>=expires||policy!=0||fault("promoter-guard")) {
        if(fault("promoter-cleanup"))*cleanup_result=-14004;
        return policy?policy:-13004;
    }
    *invoked=1;
    submissions++;
    snprintf(promoting_path,sizeof(promoting_path),"%s",relative);
    promoting=1;
    promote_polls=0;
    return fault("promoter-submit")?-14001:0;
}
int nip_promote_poll(int *state,int *result) {
    if(!promoting||fault("promoter-poll"))return -1;
    if(fault("promoter-hang")){*state=1;
        *result=-1;
        return 0;
        }
    if(promote_polls++==0){*state=1;
        *result=-1;
        return 0;
        }
    *state=0;
    if(fault("promoter-result")){*result=-14002;
        return 0;
        }
    *result=install_copy();
    if(fault("installed-corrupt")){
        char leaf[128];
        int parent=parent_at("native-installed/" NI_TITLE "/eboot.bin",leaf,1);
        int fd=parent>=0?openat(parent,leaf,O_WRONLY|O_NOFOLLOW):-1;
        if(parent>=0)close(parent);
        unsigned char changed=0xff;
        if(fd<0||pwrite(fd,&changed,1,0)!=1)*result=-14003;
        if(fd>=0&&close(fd)<0)*result=-14003;
    }
    if(fault("promoter-consume")&&*result==0){
        for(unsigned i=0;i<NI_FILE_COUNT;i++){
            char relative[256],leaf[128];
            snprintf(relative,sizeof(relative),"%s/%s",promoting_path,ni_file_names[i]);
            int parent=parent_at(relative,leaf,0);
            if(parent<0||unlinkat(parent,leaf,0)<0)*result=-14005;
            if(parent>=0)close(parent);
        }
        }
    return 0;
}
int nip_promote_finish(void) {if(fault("promoter-cleanup"))return -14004;
    promoting=0;
    return 0;
    }
static int ready(void) {char path[1200];
    snprintf(path,sizeof(path),"%s/native-idle-ready",host_root);
    struct stat st;
    return lstat(path,&st)==0&&S_ISREG(st.st_mode);
    }
int nl_idle_policy(const char *title,int absent) {return strcmp(title,NI_TITLE)||absent!=1?NL_INVALID:!ready()?NL_APP_RUNNING:fault("idle-policy")?NL_OVERLAY:0;
    }
int nl_idle_ready(void) {return nl_idle_policy(NI_TITLE,1);
    }
int nl_target_absent(const char *title) {return strcmp(title,NI_TITLE)?NL_INVALID:ready()?0:1;
    }
int nl_inventory_pid(const char *title,int32_t *pid) {(void)title;
    *pid=0;
    return NL_NOT_RUNNING;
    }
int nl_policy_status(char *out,size_t cap) {int r=nl_idle_policy(NI_TITLE,1);
    return snprintf(out,cap,"{\"app\":\"Vita Native Launch Policy\",\"protocol\":1,\"policy\":\"idle_shell_only\",\"title_id\":\"" NI_TITLE "\",\"ready\":%s,\"result\":%d,\"enumeration_result\":0,\"occupied_slots\":%d,\"state_result\":0,\"system_events\":0,\"app_events\":0,\"overlay\":0,\"state_samples_required\":2,\"snapshot_atomic\":false,\"foreground_verified\":false,\"protected_ui_verified\":false,\"native_submission_enabled\":true}",r?"false":"true",r,r?1:0);
    }
NLLaunchResult nl_launch_owned_result(const char *title,const char *build) {NLLaunchResult r={0,nl_idle_policy(title,1)};
    if(r.result)return r;
    if(!build||strlen(build)!=64){r.result=NL_INVALID;
        return r;
        }r.native_invoked=1;
    submissions++;
    r.result=fault("launch")?-15000:0;
    return r;
    }
int nl_launch_owned(const char *title,const char *build) {return nl_launch_owned_result(title,build).result;
    }
NLLaunchResult nl_launch_lab(const char *build) {return nl_launch_owned_result(NI_TITLE,build);
    }
