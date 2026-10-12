#ifndef VITA_NATIVE_INSTALL_PATHS_H
#define VITA_NATIVE_INSTALL_PATHS_H

#include <stddef.h>

#define NI_SCOPED_ROOT "ux0:data/vita-resident/n1"
#define NI_PROMOTION_ROOT "ux0:data/vita-resident/p"
#define NI_PROMOTION_PATH_MAX 128u

/* Pure C path construction shared by the Vita adapter and host assertions.
   Durable metadata stays build-scoped; only exact promotion paths use the
   short workspace. Callers still create every operation directory exclusively. */
static inline int ni_path_equal(const char *a,const char *b) {
    while(*a&&*a==*b){a++;
        b++;
    }
    return *a==*b;
}
static inline int ni_path_hex(const char *text,size_t size) {
    if(!text)return 0;
    for(size_t i=0;i<size;i++)if(!((text[i]>='0'&&text[i]<='9')||(text[i]>='a'&&text[i]<='f')))return 0;
    return 1;
}
static inline int ni_path_append(char *out,size_t cap,size_t *used,const char *text) {
    while(*text){if(*used+1>=cap)return 0;
        out[(*used)++]=*text++;
    }
    out[*used]=0;
    return 1;
}
static inline int ni_vita_path(char *out,size_t cap,const char *build,const char *relative) {
    if(!out||!cap||!build||!relative||!ni_path_hex(build,64)||build[64])return 0;
    out[0]=0;
    if(!relative[0]||relative[0]=='/')return 0;
    for(size_t i=0;relative[i];i++) {
        char c=relative[i];
        if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='/'||c=='_'||c=='-'||c=='.'))return 0;
        if(c=='.'&&relative[i+1]=='.')return 0;
        if(c=='/'&&relative[i+1]=='/')return 0;
    }
    size_t used=0;
    if(relative[0]=='p'&&(relative[1]==0||relative[1]=='/')) {
        if(!ni_path_append(out,cap,&used,NI_PROMOTION_ROOT))return 0;
        if(relative[1]) {
            const char *id=relative+2;
            if(!ni_path_hex(id,32)||(id[32]&&id[32]!='/'))return 0;
            if(id[32]) {
                const char *tail=id+33;
                static const char *const allowed[]={
                    "","sce_sys","sce_sys/livearea","sce_sys/livearea/contents","sce_sys/package",
                    "eboot.bin","sce_sys/param.sfo","sce_sys/icon0.png",
                    "sce_sys/livearea/contents/bg.png","sce_sys/livearea/contents/startup.png",
                    "sce_sys/livearea/contents/template.xml","LICENSE","sce_sys/package/head.bin"};
                int found=0;
                for(size_t i=0;i<sizeof(allowed)/sizeof(allowed[0]);i++)if(ni_path_equal(tail,allowed[i]))found=1;
                if(!found)return 0;
            }
            if(!ni_path_append(out,cap,&used,"/")||!ni_path_append(out,cap,&used,id))return 0;
        }
        return used<NI_PROMOTION_PATH_MAX;
    }
    return ni_path_append(out,cap,&used,NI_SCOPED_ROOT)
        &&ni_path_append(out,cap,&used,"/")
        &&ni_path_append(out,cap,&used,build)
        &&ni_path_append(out,cap,&used,"/")
        &&ni_path_append(out,cap,&used,relative);
}

#endif
