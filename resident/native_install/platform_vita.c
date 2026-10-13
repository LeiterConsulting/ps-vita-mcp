#include "platform.h"
#include "service.h"
#include "paths.h"
#include "../platform.h"
#include "../native_launch/native_launch.h"
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/io/dirent.h>
#include <psp2/appmgr.h>
#include <psp2/sysmodule.h>
#include <psp2/promoterutil.h>

extern const char *const ni_file_names[NI_FILE_COUNT];
static int promoter_owned,promoter_initialized,promoter_uncertain;

static int path(char out[384],const char *relative) {
    return ni_vita_path(out,384,R_BUILD_ID,relative)?0:-1;
}
static int directory(const char *p) {
    SceIoStat st={0};
    int r=sceIoGetstat(p,&st);
    if(r==(int)0x80010002u) {
        if(sceIoMkdir(p,0700|SCE_S_IRSYS|SCE_S_IWSYS)<0)return -1;
        r=sceIoGetstat(p,&st);
    }
    return r>=0&&SCE_S_ISDIR(st.st_mode)?0:-1;
}
int nip_init(void) {
    char root[384];
    if(directory("ux0:data")||directory("ux0:data/vita-resident")||directory(NI_SCOPED_ROOT)||directory(NI_PROMOTION_ROOT))return -1;
    int n=R_SNPRINTF(root,sizeof(root),NI_SCOPED_ROOT "/%s",R_BUILD_ID);
    return n>0&&(unsigned)n<sizeof(root)?directory(root):-1;
}
int nip_kind(const char *relative,uint64_t *bytes) {
    char p[384];
    SceIoStat st={0};
    if(path(p,relative))return -1;
    int r=sceIoGetstat(p,&st);
    if(r==(int)0x80010002u)return 0;
    if(r<0||st.st_size<0)return -1;
    if(bytes)*bytes=(uint64_t)st.st_size;
    return SCE_S_ISREG(st.st_mode)?1:SCE_S_ISDIR(st.st_mode)?2:-1;
}
int nip_mkdir(const char *relative) {
    char p[384];
    if(path(p,relative))return -1;
    int k=nip_kind(relative,0);
    if(k)return k==2?1:-1;
    return sceIoMkdir(p,0700|SCE_S_IRSYS|SCE_S_IWSYS)<0?-1:0;
}
int nip_open_read(const char *relative) {
    char p[384];
    if(path(p,relative)||nip_kind(relative,0)!=1)return -1;
    return sceIoOpen(p,SCE_O_RDONLY|SCE_O_NBLOCK,0);
}
int nip_open_new(const char *relative) {
    char p[384];
    if(path(p,relative)||nip_kind(relative,0)!=0)return -1;
    return sceIoOpen(p,SCE_O_WRONLY|SCE_O_CREAT|SCE_O_EXCL,0600|SCE_S_IRSYS|SCE_S_IWSYS);
}
int nip_read(int fd,void *out,size_t n) {return sceIoRead(fd,out,n);
    }
int nip_write(int fd,const void *data,size_t n) {return sceIoWrite(fd,data,n);
    }
int nip_size(int fd,uint64_t *bytes) {
    SceIoStat st={0};
    if(!bytes||sceIoGetstatByFd(fd,&st)<0||!SCE_S_ISREG(st.st_mode)||st.st_size<0)return -1;
    *bytes=(uint64_t)st.st_size;
    return 0;
}
int nip_sync(int fd) {return sceIoSyncByFd(fd,0);
    }
int nip_close(int fd) {return sceIoClose(fd);
    }
int nip_sync_device(void) {return sceIoSync("ux0:",0);
    }
int nip_rename_new(const char *from,const char *to) {
    char a[384],b[384];
    if(path(a,from)||path(b,to)||nip_kind(from,0)!=1||nip_kind(to,0)!=0)return -1;
    return sceIoRename(a,b);
}
int nip_list(const char *relative,unsigned index,char out[64]) {
    char p[384];
    if(path(p,relative)||nip_kind(relative,0)!=2)return -1;
    int fd=sceIoDopen(p);
    if(fd<0)return -1;
    unsigned seen=0;
    int result=-1;
    for(unsigned bound=0;bound<132;bound++) {
        SceIoDirent ent;
        R_MEMSET(&ent,0,sizeof(ent));
        int n=sceIoDread(fd,&ent);
        if(n<=0){result=n<0?-1:0;
            break;
            }
        if(!R_STRCMP(ent.d_name,".")||!R_STRCMP(ent.d_name,".."))continue;
        if(seen++!=index)continue;
        size_t length=R_STRLEN(ent.d_name);
        if(length>=64){result=-1;
            break;
            }
        R_MEMCPY(out,ent.d_name,length+1);
        result=1;
        break;
    }
    if(sceIoDclose(fd)<0)return -1;
    return result;
}
int nip_free(uint64_t *bytes) {uint64_t capacity=0;
    return sceAppMgrGetDevInfo("ux0:",&capacity,bytes);
    }
int nip_installed_kind(void) {
    SceIoStat st={0};
    int r=sceIoGetstat("ux0:app/" NI_TITLE,&st);
    if(r==(int)0x80010002u)return 0;
    return r>=0&&SCE_S_ISDIR(st.st_mode)?2:-1;
}
int nip_installed_open(unsigned index) {
    if(index>=NI_FILE_COUNT)return -1;
    char p[192];
    int n=R_SNPRINTF(p,sizeof(p),"ux0:app/" NI_TITLE "/%s",ni_file_names[index]);
    SceIoStat st={0};
    if(n<=0||(unsigned)n>=sizeof(p)||sceIoGetstat(p,&st)<0||!SCE_S_ISREG(st.st_mode))return -1;
    return sceIoOpen(p,SCE_O_RDONLY|SCE_O_NBLOCK,0);
}
int nip_promote_available(int *paf_result,int *promoter_result) {
    if(!paf_result||!promoter_result)return 0;
    *paf_result=sceSysmoduleIsLoadedInternal(SCE_SYSMODULE_INTERNAL_PAF);
    *promoter_result=sceSysmoduleIsLoadedInternal(SCE_SYSMODULE_INTERNAL_PROMOTER_UTIL);
    return *paf_result==0&&*promoter_result==(int)SCE_SYSMODULE_ERROR_UNLOADED&&!promoter_owned&&!promoter_uncertain;
}
int nip_promote_start(const char *relative,uint64_t issued,uint64_t expires,int *invoked,int *cleanup_result) {
    if(invoked)*invoked=0;
    if(cleanup_result)*cleanup_result=0;
    char p[384];
    if(!invoked||!cleanup_result||path(p,relative)||R_STRLEN(p)>=128||promoter_owned||promoter_uncertain)return -13000;
    if(sceSysmoduleIsLoadedInternal(SCE_SYSMODULE_INTERNAL_PAF)!=0)return -13001;
    if(sceSysmoduleIsLoadedInternal(SCE_SYSMODULE_INTERNAL_PROMOTER_UTIL)!=(int)SCE_SYSMODULE_ERROR_UNLOADED)return -13002;
    int r=sceSysmoduleLoadModuleInternal(SCE_SYSMODULE_INTERNAL_PROMOTER_UTIL);
    if(r<0)return r;
    promoter_owned=1;
    r=scePromoterUtilityInit();
    if(r<0){int cleanup=sceSysmoduleUnloadModuleInternal(SCE_SYSMODULE_INTERNAL_PROMOTER_UTIL);
        *cleanup_result=cleanup;
        if(cleanup>=0)promoter_owned=0;
        else promoter_uncertain=1;
        return r;
        }
    promoter_initialized=1;
    int policy=nl_idle_policy(NI_TITLE,1);
    uint64_t now=r_pair_mono();
    if(issued>now||now-issued>5000||now>=expires||policy!=0) {
        *cleanup_result=nip_promote_finish();
        return policy?policy:-13004;
    }
    *invoked=1;
    r=scePromoterUtilityPromotePkgWithRif(p,0);
    if(r<0)promoter_uncertain=1;
    return r;
}
int nip_promote_poll(int *state,int *result) {
    if(!state||!result||!promoter_owned||!promoter_initialized||promoter_uncertain)return -1;
    *state=-1;
    *result=-1;
    if(scePromoterUtilityGetState(state)<0||*state<0){promoter_uncertain=1;
        return -1;
        }
    if(!*state&&scePromoterUtilityGetResult(result)<0){promoter_uncertain=1;
        return -1;
        }
    return 0;
}
int nip_promote_finish(void) {
    if(!promoter_owned||!promoter_initialized||promoter_uncertain)return -1;
    int r=scePromoterUtilityExit();
    if(r<0){promoter_uncertain=1;
        return r;
        }
    promoter_initialized=0;
    r=sceSysmoduleUnloadModuleInternal(SCE_SYSMODULE_INTERNAL_PROMOTER_UTIL);
    if(r<0){promoter_uncertain=1;
        return r;
        }
    promoter_owned=0;
    return 0;
}
