/* Fixed owned-title installation; serialized, allocation-free, no boot effects. */
#include "service.h"
#include "platform.h"
#include "../platform.h"
#include "../sha256.h"
#include "../launch_broker/native.h"
#include "../native_launch/native_launch.h"
#include <limits.h>

const char *const ni_file_names[NI_FILE_COUNT]={
    "eboot.bin","sce_sys/param.sfo","sce_sys/icon0.png",
    "sce_sys/livearea/contents/bg.png","sce_sys/livearea/contents/startup.png",
    "sce_sys/livearea/contents/template.xml","LICENSE","sce_sys/package/head.bin"};
typedef struct {uint64_t bytes;
    char sha[65];
    } NIFile;
typedef struct {
    char raw[NI_MAX_BODY+1],sha[65],attempt[33],instance[33],resident[65];
    char version[6],build[65],package_sha[65];
    uint64_t package_bytes,issued,ttl,total;
    NIFile files[NI_FILE_COUNT];
    size_t raw_size;
} Manifest;
typedef struct {
    char attempt[33],stage[33],kind[8],state[32],raw[NI_MAX_BODY+1];
    char instance[33],resident[65],manifest_sha[65];
    uint64_t issued,expires,started;
    unsigned dispatch;
    int native_result,operation_result,cleanup_result,invoked,installed;
    Manifest candidate;
    int present;
} Operation;
typedef struct {const char *p,*end;
    } Parser;
static char instance[33];static int initialized,blocked;
static Manifest scratch;static Operation active;
static unsigned char chunk[16384];
static int busy(void) {return active.present&&(!R_STRCMP(active.state,"queued")||!R_STRCMP(active.state,"dispatch_intent")||!R_STRCMP(active.state,"running"));
    }

static int hex(const char *s,unsigned n) {
    if(!s||R_STRLEN(s)!=n)return 0;
    for(unsigned i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return 1;
}
static int equal(const void *a,const void *b,size_t n) {
    const unsigned char *x=a,*y=b;
    unsigned d=0;
    for(size_t i=0;i<n;i++)d|=(unsigned)(x[i]^y[i]);
    return !d;
}
static void sha(const void *data,size_t n,char out[65]) {RSha h;
    rs_init(&h);
    rs_update(&h,data,n);
    rs_final(&h,out);
    }
static void white(Parser *p) {while(p->p<p->end&&(*p->p==' '||*p->p=='\n'||*p->p=='\r'||*p->p=='\t'))p->p++;
    }
static int token(Parser *p,char c) {white(p);
    if(p->p==p->end||*p->p!=c)return 0;
    p->p++;
    return 1;
    }
static int string(Parser *p,char *out,size_t cap) {
    if(!token(p,'"'))return 0;
    size_t n=0;
    while(p->p<p->end&&*p->p!='"') {
        unsigned char c=(unsigned char)*p->p++;
        if(c<32||c>126||c=='\\'||n+1>=cap)return 0;
        out[n++]=(char)c;
    }
    if(p->p==p->end)return 0;
    p->p++;
    out[n]=0;
    return 1;
}
static int number(Parser *p,uint64_t *value) {
    white(p);
    if(p->p==p->end||*p->p<'0'||*p->p>'9')return 0;
    if(*p->p=='0'&&p->p+1<p->end&&p->p[1]>='0'&&p->p[1]<='9')return 0;
    uint64_t v=0;
    while(p->p<p->end&&*p->p>='0'&&*p->p<='9') {
        unsigned d=(unsigned)(*p->p++-'0');
        if(v>(UINT64_MAX-d)/10)return 0;
        v=v*10+d;
    }
    *value=v;
    return 1;
}
static int end(Parser *p) {white(p);
    return p->p==p->end;
    }
static int field_end(Parser *p) {white(p);
    if(p->p==p->end)return -1;
    if(*p->p=='}'){p->p++;
        return 1;
        }return token(p,',')?0:-1;
    }
static int file_parse(Parser *p,NIFile *f) {
    if(!token(p,'{'))return 0;
    unsigned seen=0;
    for(;;) {
        char key[32];
        if(!string(p,key,sizeof(key))||!token(p,':'))return 0;
        if(!R_STRCMP(key,"bytes")){if(seen&1||!number(p,&f->bytes)||!f->bytes||f->bytes>NI_MAX_FILE)return 0;
            seen|=1;
            }
        else if(!R_STRCMP(key,"sha256")){if(seen&2||!string(p,f->sha,sizeof(f->sha))||!hex(f->sha,64))return 0;
            seen|=2;
            }
        else return 0;
        int next=field_end(p);
        if(next<0)return 0;
        if(next)return seen==3;
    }
}
static int manifest_parse(const void *body,size_t size,Manifest *m) {
    if(!body||!size||size>NI_MAX_BODY)return 0;
    R_MEMSET(m,0,sizeof(*m));
    Parser p={body,(const char *)body+size};
    if(!token(&p,'{'))return 0;
    unsigned seen=0;
    for(;;) {
        char key[64],text[80];
        uint64_t value;
        unsigned bit;
        if(!string(&p,key,sizeof(key))||!token(&p,':'))return 0;
        const char *keys[]={"protocol","project","title_id","version","native_build_id","package_sha256","package_bytes","resident_build_id","instance_id","attempt","issued_ms","ttl_ms","files"};
        for(bit=0;bit<13;bit++)if(!R_STRCMP(key,keys[bit]))break;
        if(bit==13||(seen&(1u<<bit)))return 0;
        seen|=1u<<bit;
        if(bit==0){if(!number(&p,&value)||value!=1)return 0;
            }
        else if(bit==6){if(!number(&p,&m->package_bytes)||!m->package_bytes||m->package_bytes>NI_MAX_FILE)return 0;
            }
        else if(bit==10){if(!number(&p,&m->issued))return 0;
            }
        else if(bit==11){if(!number(&p,&m->ttl)||!m->ttl||m->ttl>30000)return 0;
            }
        else if(bit==12) {
            if(!token(&p,'['))return 0;
            for(unsigned i=0;i<NI_FILE_COUNT;i++) {
                if(i&&!token(&p,','))return 0;
                if(!file_parse(&p,&m->files[i])||m->total>NI_MAX_TOTAL-m->files[i].bytes)return 0;
                m->total+=m->files[i].bytes;
            }
            if(!token(&p,']'))return 0;
        } else {
            if(!string(&p,text,sizeof(text)))return 0;
            if(bit==1){if(R_STRCMP(text,NI_PROJECT))return 0;
                }
            else if(bit==2){if(R_STRCMP(text,NI_TITLE))return 0;
                }
            else if(bit==3){if(R_STRLEN(text)!=5||text[2]!='.'||text[0]<'0'||text[0]>'9'||text[1]<'0'||text[1]>'9'||text[3]<'0'||text[3]>'9'||text[4]<'0'||text[4]>'9')return 0;
                R_MEMCPY(m->version,text,6);
                }
            else if(bit==4){if(!hex(text,64))return 0;
                R_MEMCPY(m->build,text,65);
                }
            else if(bit==5){if(!hex(text,64))return 0;
                R_MEMCPY(m->package_sha,text,65);
                }
            else if(bit==7){if(!hex(text,64))return 0;
                R_MEMCPY(m->resident,text,65);
                }
            else if(bit==8){if(!hex(text,32))return 0;
                R_MEMCPY(m->instance,text,33);
                }
            else if(bit==9){if(!hex(text,32))return 0;
                R_MEMCPY(m->attempt,text,33);
                }
        }
        int next=field_end(&p);
        if(next<0)return 0;
        if(next)break;
    }
    if(seen!=8191u||!end(&p)||m->files[0].bytes<0x88||m->files[1].bytes>16384||m->files[7].bytes!=0x430)return 0;
    m->raw_size=size;
    R_MEMCPY(m->raw,body,size);
    m->raw[size]=0;
    sha(body,size,m->sha);
    return 1;
}
static int operation_parse(const void *body,size_t size,Operation *o) {
    if(!body||!size||size>NI_MAX_BODY)return 0;
    R_MEMSET(o,0,sizeof(*o));
    o->native_result=o->operation_result=-1;
    Parser p={body,(const char *)body+size};
    if(!token(&p,'{'))return 0;
    unsigned seen=0;
    uint64_t ttl=0;
    for(;;) {
        char key[64],value[80];
        unsigned bit;
        if(!string(&p,key,sizeof(key))||!token(&p,':'))return 0;
        const char *keys[]={"manifest_sha256","resident_build_id","instance_id","issued_ms","ttl_ms","attempt"};
        for(bit=0;bit<6;bit++)if(!R_STRCMP(key,keys[bit]))break;
        if(bit==6||(seen&(1u<<bit)))return 0;
        seen|=1u<<bit;
        if(bit==3){if(!number(&p,&o->issued))return 0;
            }
        else if(bit==4){if(!number(&p,&ttl)||!ttl||ttl>30000)return 0;
            }
        else {
            if(!string(&p,value,sizeof(value))||!hex(value,bit==2||bit==5?32:64))return 0;
            char *target=bit==0?o->manifest_sha:bit==1?o->resident:bit==2?o->instance:o->attempt;
            R_MEMCPY(target,value,bit==2||bit==5?33:65);
        }
        int next=field_end(&p);
        if(next<0)return 0;
        if(next)break;
    }
    if(seen!=63u||!end(&p)||o->issued>UINT64_MAX-ttl)return 0;
    o->expires=o->issued+ttl;
    R_MEMCPY(o->raw,body,size);
    o->raw[size]=0;
    return 1;
}
static int fresh(uint64_t issued,uint64_t expires) {
    uint64_t now=r_pair_mono();
    return issued<=now&&now-issued<=5000&&now<expires;
}
static int path_stage(char out[192],const char *id,const char *tail) {
    if(!hex(id,32))return 0;
    int n=R_SNPRINTF(out,192,"stages/%s/%s",id,tail);
    return n>0&&n<192;
}
static int path_op(char out[192],const char *id,const char *tail) {
    if(!hex(id,32))return 0;
    int n=R_SNPRINTF(out,192,"attempts/%s/%s",id,tail);
    return n>0&&n<192;
}
/* Immutable checksummed envelopes: complete bytes, fd/device sync, then exact
   independent readback. A partial file is retained and refuses a repeated ID. */
static int record_read(const char *path,char *out,size_t cap,size_t *length) {
    int fd=nip_open_read(path);
    if(fd<0)return -1;
    uint64_t bytes=0;
    int good=nip_size(fd,&bytes)==0&&bytes>=65&&bytes<cap+65;
    size_t payload=good?(size_t)bytes-65:0,used=0;
    char digest[65]={0};
    while(good&&used<payload){int n=nip_read(fd,out+used,payload-used);
        if(n<=0||(size_t)n>payload-used){good=0;
            break;
            }used+=(size_t)n;
        }
    char ending[65];
    used=0;
    while(good&&used<65){int n=nip_read(fd,ending+used,65-used);
        if(n<=0||(size_t)n>65-used){good=0;
            break;
            }used+=(size_t)n;
        }
    uint64_t after=0;
    if(good&&(nip_size(fd,&after)||after!=bytes))good=0;
    if(nip_close(fd)<0)good=0;
    if(!good)return -1;
    sha(out,payload,digest);
    if(ending[0]!='\n'||!equal(digest,ending+1,64))return -1;
    out[payload]=0;
    if(length)*length=payload;
    return 0;
}
static int record_write(const char *path,const void *data,size_t size) {
    if(size>NI_MAX_BODY)return -1;
    int fd=nip_open_new(path);
    if(fd<0)return -1;
    char digest[65],ending[65];
    sha(data,size,digest);
    ending[0]='\n';
    R_MEMCPY(ending+1,digest,64);
    const unsigned char *p=data;
    size_t used=0;
    int good=1;
    while(used<size){int n=nip_write(fd,p+used,size-used);
        if(n<=0||(size_t)n>size-used){good=0;
            break;
            }used+=(size_t)n;
        }
    if(good&&nip_write(fd,ending,65)!=65)good=0;
    if(good&&nip_sync(fd)<0)good=0;
    if(nip_close(fd)<0)good=0;
    if(good&&nip_sync_device()<0)good=0;
    char check[NI_MAX_BODY+1];
    size_t observed=0;
    if(!good||record_read(path,check,sizeof(check),&observed)||observed!=size||!equal(check,data,size))return -1;
    return 0;
}
static int load_stage(const char *id,Manifest *m) {
    char path[192],raw[NI_MAX_BODY+1];
    size_t size=0;
    if(!path_stage(path,id,"manifest.json")||record_read(path,raw,sizeof(raw),&size)||!manifest_parse(raw,size,m)||R_STRCMP(m->attempt,id)||R_STRCMP(m->resident,R_BUILD_ID))return -1;
    return 0;
}
static int file_hash(int fd,uint64_t wanted,const char *expected,const char *build) {
    uint64_t before=0,after=0,total=0,deadline=r_pair_mono()+10000;
    RSha h;
    rs_init(&h);
    unsigned match=0;
    char marker[96]={0};
    size_t marker_size=0;
    if(build){int n=R_SNPRINTF(marker,sizeof(marker),"VITA_NATIVE_LIFECYCLE_LAB:%s",build);
        if(n<=0||(unsigned)n>=sizeof(marker)){nip_close(fd);
            return -1;
        }
        marker_size=(unsigned)n;
    }
    int found=build?0:1,good=nip_size(fd,&before)==0&&before==wanted;
    while(good&&total<wanted) {
        if(r_pair_mono()>=deadline){good=0;
            break;
            }
        size_t ask=wanted-total<sizeof(chunk)?(size_t)(wanted-total):sizeof(chunk);
        int n=nip_read(fd,chunk,ask);
        if(n<=0||(size_t)n>ask){good=0;
            break;
            }
        if(build)for(int j=0;j<n;j++){unsigned char c=chunk[j];
            if(c==(unsigned char)marker[match]){if(++match==marker_size){found=1;
                    match=0;
                    }}else match=c==(unsigned char)marker[0]?1u:0u;
            }
        rs_update(&h,chunk,(size_t)n);
        total+=(unsigned)n;
    }
    if(good&&(nip_size(fd,&after)||after!=before))good=0;
    if(nip_close(fd)<0)good=0;
    char observed[65];
    rs_final(&h,observed);
    return good&&found&&total==wanted&&!R_STRCMP(observed,expected)?0:-1;
}
static int file_path(char out[192],const Manifest *m,unsigned index,int part) {
    char tail[128];
    int n=R_SNPRINTF(tail,sizeof(tail),"package/%s%s",ni_file_names[index],part?".part":"");
    return n>0&&(unsigned)n<sizeof(tail)&&path_stage(out,m->attempt,tail);
}
static int verify_file(const Manifest *m,unsigned index,int installed) {
    char path[192];
    int fd;
    if(installed)fd=nip_installed_open(index);
    else {if(!file_path(path,m,index,0))return -1;
        fd=nip_open_read(path);
        }
    return fd<0?-1:file_hash(fd,m->files[index].bytes,m->files[index].sha,index==0?m->build:0);
}
static uint32_t le32(const unsigned char *p) {return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
    }
static unsigned le16(const unsigned char *p) {return p[0]|(unsigned)p[1]<<8;
    }
static int read_small(const Manifest *m,unsigned index,unsigned char *out,size_t cap) {
    char path[192];
    if(!file_path(path,m,index,0)||m->files[index].bytes>cap)return -1;
    int fd=nip_open_read(path);
    if(fd<0)return -1;
    size_t used=0,wanted=(size_t)m->files[index].bytes;
    int good=1;
    while(used<wanted){int n=nip_read(fd,out+used,wanted-used);
        if(n<=0||(size_t)n>wanted-used){good=0;
            break;
            }used+=(size_t)n;
        }
    if(nip_close(fd)<0)good=0;
    return good?(int)used:-1;
}
static int sfo_matches(const Manifest *m) {
    unsigned char data[16384];
    int n=read_small(m,1,data,sizeof(data));
    if(n<20)return 0;
    unsigned size=(unsigned)n;
    uint32_t keys=le32(data+8),values=le32(data+12),count=le32(data+16);
    if(le32(data)!=0x46535000||le32(data+4)!=0x101||count>64||20+count*16>size||keys<20+count*16||keys>=values||values>=size)return 0;
    unsigned seen=0;
    for(unsigned i=0;i<count;i++) {
        const unsigned char *e=data+20+16*i;
        uint32_t key=keys+le16(e),length=le32(e+4),maximum=le32(e+8),offset=le32(e+12);
        unsigned fmt=le16(e+2);
        if(key<keys||key>=values||offset>size-values||length>maximum||maximum>size-values-offset||!length)return 0;
        unsigned endkey=key;
        while(endkey<values&&data[endkey])endkey++;
        if(endkey==values)return 0;
        for(unsigned j=0;j<i;j++){uint32_t old=keys+le16(data+20+16*j);
            if(!R_STRCMP((const char *)data+key,(const char *)data+old))return 0;
            }
        const char *name=(const char *)data+key;
        const unsigned char *v=data+values+offset;
        unsigned bit=!R_STRCMP(name,"TITLE_ID")?1u:!R_STRCMP(name,"APP_VER")?2u:!R_STRCMP(name,"CATEGORY")?4u:!R_STRCMP(name,"PSP2_SYSTEM_VER")?8u:0u;
        if(!bit)continue;
        if(bit==8){if(fmt!=0x404||length!=4||le32(v)>0x03650000)return 0;
            }
        else {const char *wanted=bit==1?NI_TITLE:bit==2?m->version:"gd";
            size_t want=R_STRLEN(wanted);
            if(fmt!=0x204||length!=want+1||!equal(v,wanted,want+1))return 0;
            }
        seen|=bit;
    }
    return seen==15;
}
static int package_identity(const Manifest *m) {
    unsigned char head[0x430];
    char path[192];
    if(!file_path(path,m,0,0))return 0;
    int fd=nip_open_read(path);
    if(fd<0)return 0;
    int n=nip_read(fd,head,0x88);
    int good=n==0x88&&equal(head,"SCE\0",4)&&le32(head+0x80)==1&&le32(head+0x84)==0x2f000000;
    if(nip_close(fd)<0)good=0;
    if(!good||!sfo_matches(m)||read_small(m,7,head,sizeof(head))!=0x430||!equal(head,"\x7fPKG",4))return 0;
    return equal(head+0x30,"EP9000-" NI_TITLE "_00-0000000000000000",36);
}
static int tree_exact(const Manifest *m) {
    static const char *dirs[]={"","sce_sys","sce_sys/livearea","sce_sys/livearea/contents","sce_sys/package"};
    for(unsigned d=0;d<5;d++) {
        char tail[160],path[192],member_path[192];
        R_SNPRINTF(tail,sizeof(tail),"package%s%s",d?"/":"",dirs[d]);
        if(!path_stage(path,m->attempt,tail)||nip_kind(path,0)!=2){
#ifdef NI_CORE_TEST
            fprintf(stderr,"tree directory %s kind %d\n",path,nip_kind(path,0));
#endif
            return 0;
        }
        for(unsigned index=0;index<16;index++) {
            char entry[64];
            int result=nip_list(path,index,entry);
            if(result<0){
#ifdef NI_CORE_TEST
                fprintf(stderr,"tree list failed %s index %u\n",path,index);
#endif
                return 0;
            }
            if(!result)break;
            char member[128];
            R_SNPRINTF(member,sizeof(member),"%s%s%s",dirs[d],d?"/":"",entry);
            int allowed=0,kind=0;
            for(unsigned f=0;f<NI_FILE_COUNT;f++)if(!R_STRCMP(member,ni_file_names[f])){allowed=1;
                kind=1;
                }
            for(unsigned sub=1;sub<5;sub++)if(!R_STRCMP(member,dirs[sub])){allowed=1;
                kind=2;
                }
            R_SNPRINTF(tail,sizeof(tail),"package/%s",member);
            if(!allowed||!path_stage(member_path,m->attempt,tail)||nip_kind(member_path,0)!=kind){
#ifdef NI_CORE_TEST
                fprintf(stderr,"tree member %s allowed %d expected %d path %s actual %d\n",member,allowed,kind,member_path,nip_kind(member_path,0));
#endif
                return 0;
            }
            if(index==15)return 0;
        }
    }
    return 1;
}
static int verify_candidate(const Manifest *m) {
    if(!tree_exact(m)){
#ifdef NI_CORE_TEST
        fprintf(stderr,"candidate diagnostic: tree\n");
#endif
        return 0;
    }
    for(unsigned i=0;i<NI_FILE_COUNT;i++)if(verify_file(m,i,0)){
#ifdef NI_CORE_TEST
        fprintf(stderr,"candidate diagnostic: file %u\n",i);
#endif
        return 0;
    }
#ifdef NI_CORE_TEST
    if(!package_identity(m))fprintf(stderr,"candidate diagnostic: identity\n");
#endif
    return package_identity(m);
}
static int verify_installed(const Manifest *m) {
    if(nip_installed_kind()!=2)return 0;
    for(unsigned i=0;i<NI_FILE_COUNT;i++)if(verify_file(m,i,1))return 0;
    return 1;
}
/* The system promoter may move/consume its source tree. Give each operation
   a fresh fully verified working copy; retain the original stage unchanged. */
static int promotion_copy(const Manifest *m,const char *operation,char out[192]) {
    char tail[160],path[192];
    if(!hex(operation,32)||nip_mkdir("p")<0)return 0;
    int n=R_SNPRINTF(path,sizeof(path),"p/%s",operation);
    if(n<=0||(unsigned)n>=sizeof(path)||nip_mkdir(path)!=0)return 0;
    const char *dirs[]={"sce_sys","sce_sys/livearea","sce_sys/livearea/contents","sce_sys/package"};
    for(unsigned i=0;i<4;i++) {
        n=R_SNPRINTF(path,sizeof(path),"p/%s/%s",operation,dirs[i]);
        if(n<=0||(unsigned)n>=sizeof(path)||nip_mkdir(path)!=0)return 0;
    }
    uint64_t deadline=r_pair_mono()+30000;
    for(unsigned index=0;index<NI_FILE_COUNT;index++) {
        char source[192];
        if(!file_path(source,m,index,0))return 0;
        n=R_SNPRINTF(path,sizeof(path),"p/%s/%s",operation,ni_file_names[index]);
        if(n<=0||(unsigned)n>=sizeof(path))return 0;
        int in=nip_open_read(source);
        if(in<0)return 0;
        int dest=nip_open_new(path);
        if(dest<0){nip_close(in);
            return 0;
            }
        uint64_t total=0;
        int good=1;
        while(total<m->files[index].bytes) {
            if(r_pair_mono()>=deadline){good=0;
                break;
                }
            size_t ask=m->files[index].bytes-total<sizeof(chunk)?(size_t)(m->files[index].bytes-total):sizeof(chunk);
            int got=nip_read(in,chunk,ask);
            if(got<=0||(size_t)got>ask){good=0;
                break;
                }
            size_t used=0;
            while(used<(size_t)got){int wrote=nip_write(dest,chunk+used,(size_t)got-used);
                if(wrote<=0||(size_t)wrote>(size_t)got-used){good=0;
                    break;
                    }used+=(size_t)wrote;
                }
            if(!good)break;
            total+=(unsigned)got;
        }
        if(good&&nip_sync(dest)<0)good=0;
        if(nip_close(in)<0)good=0;
        if(nip_close(dest)<0)good=0;
        if(good&&nip_sync_device()<0)good=0;
        int check=good?nip_open_read(path):-1;
        if(!good||check<0||file_hash(check,m->files[index].bytes,m->files[index].sha,index==0?m->build:0))return 0;
    }
    n=R_SNPRINTF(tail,sizeof(tail),"p/%s",operation);
    if(n<=0||(unsigned)n>=sizeof(tail))return 0;
    R_MEMCPY(out,tail,(unsigned)n+1);
    return 1;
}
static int count_entries(const char *directory,unsigned limit) {
    for(unsigned i=0;i<=limit;i++){char name[64];
        int n=nip_list(directory,i,name);
        if(n<0)return -1;
        if(!n)return (int)i;
        if(!hex(name,32)||i==limit)return -1;
        }
    return -1;
}
static int receipt(char *out,size_t cap,const Operation *o) {
    int n=R_SNPRINTF(out,cap,"{\"app\":\"Vita Native Lifecycle\",\"protocol\":1,\"attempt\":\"%s\",\"stage_attempt\":\"%s\",\"operation\":\"%s\",\"manifest_sha256\":\"%s\",\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"issued_ms\":%llu,\"expires_ms\":%llu,\"state\":\"%s\",\"dispatch_count\":%u,\"native_invoked\":%s,\"native_result\":%d,\"operation_result\":%d,\"cleanup_result\":%d,\"installed_verified\":%s,\"may_have_effects\":%s}",o->attempt,o->stage,o->kind,o->manifest_sha,o->resident,o->instance,(unsigned long long)o->issued,(unsigned long long)o->expires,o->state,o->dispatch,o->invoked?"true":"false",o->native_result,o->operation_result,o->cleanup_result,o->installed?"true":"false",o->invoked||(!R_STRCMP(o->state,"unknown")&&o->dispatch)?"true":"false");
    return n>0&&(size_t)n<cap?n:-1;
}
static void terminal(const char *state) {
    R_SNPRINTF(active.state,sizeof(active.state),"%s",state);
    char data[NI_MAX_BODY+1],path[192];
    int n=receipt(data,sizeof(data),&active);
    if(!R_STRCMP(state,"unknown"))blocked=1;
    if(n<0||!path_op(path,active.attempt,"final.json")||record_write(path,data,(size_t)n)) {blocked=1;
        R_SNPRINTF(active.state,sizeof(active.state),"unknown");
        }
}
static int claim_read(const char *id,Operation *o) {
    char path[192],data[NI_MAX_BODY+1];
    size_t size;
    if(!path_op(path,id,"claim.json")||record_read(path,data,sizeof(data),&size)||size<42)return 0;
    if(data[32]!='\n')return 0;
    char stage[33];
    R_MEMCPY(stage,data,32);
    stage[32]=0;
    const char *kind=data+33;
    const char *line=R_STRCHR(kind,'\n');
    if(!line||line-kind>7)return 0;
    char operation[8];
    R_MEMCPY(operation,kind,(size_t)(line-kind));
    operation[line-kind]=0;
    if((R_STRCMP(operation,"install")&&R_STRCMP(operation,"launch"))||!hex(stage,32)||!operation_parse(line+1,size-(size_t)(line+1-data),o)||R_STRCMP(o->attempt,id)||R_STRCMP(o->resident,R_BUILD_ID))return 0;
    R_MEMCPY(o->stage,stage,33);
    R_SNPRINTF(o->kind,sizeof(o->kind),"%s",operation);
    return 1;
}
static int signed_number(Parser *p,int *out) {
    white(p);
    int negative=p->p<p->end&&*p->p=='-';
    if(negative)p->p++;
    uint64_t value;
    if(!number(p,&value)||value>(negative?2147483648ull:2147483647ull))return 0;
    *out=negative?(value==2147483648ull?INT_MIN:-(int)value):(int)value;
    return 1;
}
static int boolean(Parser *p,int *out) {
    white(p);
    size_t left=(size_t)(p->end-p->p);
    if(left>=4&&!R_STRNCMP(p->p,"true",4)){p->p+=4;
        *out=1;
        return 1;
    }
    if(left>=5&&!R_STRNCMP(p->p,"false",5)){p->p+=5;
        *out=0;
        return 1;
    }
    return 0;
}
/* Persisted receipts are untrusted input, even when their checksum is valid.
   Bind every identity and time field to the durable claim; permit only known
   terminal outcomes and combinations produced by this implementation. */
static int invalid_receipt(unsigned line) {
#ifdef NI_CORE_TEST
    fprintf(stderr,"invalid persisted receipt line %u\n",line);
#else
    (void)line;
#endif
    return 0;
}
static int final_parse(const char *data,size_t size,Operation *o) {
    Parser p={data,data+size};
    if(!token(&p,'{'))return invalid_receipt(__LINE__);
    unsigned seen=0;
    int effects=-1;
    for(;;) {
        static const char *keys[]={"app","protocol","attempt","stage_attempt","operation","manifest_sha256","resident_build_id","instance_id","issued_ms","expires_ms","state","dispatch_count","native_invoked","native_result","operation_result","cleanup_result","installed_verified","may_have_effects"};
        char key[64],value[80];
        unsigned bit;
        uint64_t number_value;
        if(!string(&p,key,sizeof(key))||!token(&p,':'))return invalid_receipt(__LINE__);
        for(bit=0;bit<18;bit++)if(!R_STRCMP(key,keys[bit]))break;
        if(bit==18||(seen&(1u<<bit)))return invalid_receipt(__LINE__);
        seen|=1u<<bit;
        if(bit==1||bit==8||bit==9||bit==11) {
            if(!number(&p,&number_value))return invalid_receipt(__LINE__);
            if(bit==1&&number_value!=1)return invalid_receipt(__LINE__);
            if(bit==8&&number_value!=o->issued)return invalid_receipt(__LINE__);
            if(bit==9&&number_value!=o->expires)return invalid_receipt(__LINE__);
            if(bit==11){if(number_value>1)return invalid_receipt(__LINE__);
                o->dispatch=(unsigned)number_value;
            }
        } else if(bit==12||bit==16||bit==17) {
            int *target=bit==12?&o->invoked:bit==16?&o->installed:&effects;
            if(!boolean(&p,target))return invalid_receipt(__LINE__);
        } else if(bit>=13&&bit<=15) {
            int *target=bit==13?&o->native_result:bit==14?&o->operation_result:&o->cleanup_result;
            if(!signed_number(&p,target))return invalid_receipt(__LINE__);
        } else {
            if(!string(&p,value,sizeof(value)))return invalid_receipt(__LINE__);
            if(bit==10){if(R_STRLEN(value)>=sizeof(o->state))return invalid_receipt(__LINE__);
                R_MEMCPY(o->state,value,R_STRLEN(value)+1);
            } else {
                const char *expected=bit==0?"Vita Native Lifecycle":bit==2?o->attempt:bit==3?o->stage:bit==4?o->kind:bit==5?o->manifest_sha:bit==6?o->resident:o->instance;
                if(R_STRCMP(value,expected))return invalid_receipt(__LINE__);
            }
        }
        int next=field_end(&p);
        if(next<0)return invalid_receipt(__LINE__);
        if(next)break;
    }
    if(seen!=262143u||!end(&p)||o->invoked>(int)o->dispatch)return invalid_receipt(__LINE__);
    int unknown=!R_STRCMP(o->state,"unknown");
    int installed=!R_STRCMP(o->state,"installed_verified");
    int submitted=!R_STRCMP(o->state,"submitted");
    int rejected=!R_STRCMP(o->state,"native_rejected");
    int refused=!R_STRCMP(o->state,"refused");
    int expired=!R_STRCMP(o->state,"expired");
    if(!unknown&&!installed&&!submitted&&!rejected&&!refused&&!expired)return invalid_receipt(__LINE__);
    if(effects!=(o->invoked||(unknown&&o->dispatch)))return invalid_receipt(__LINE__);
    if(installed) {
        if(R_STRCMP(o->kind,"install")||!o->invoked||o->native_result<0||o->operation_result!=0||o->cleanup_result<0||!o->installed)return invalid_receipt(__LINE__);
    } else if(o->installed)return invalid_receipt(__LINE__);
    if(submitted&&(R_STRCMP(o->kind,"launch")||!o->invoked||o->native_result<0||o->operation_result!=o->native_result||o->cleanup_result!=0))return invalid_receipt(__LINE__);
    if(rejected&&(!o->invoked||o->cleanup_result<0||(!R_STRCMP(o->kind,"install")?o->operation_result>=0:o->native_result>=0)))return invalid_receipt(__LINE__);
    if((refused||expired)&&(o->invoked||o->cleanup_result<0))return invalid_receipt(__LINE__);
    if(!unknown) {
        char path[192],intent[65];
        size_t intent_size;
        if(!path_op(path,o->attempt,"intent"))return invalid_receipt(__LINE__);
        if(o->dispatch) {
            if(record_read(path,intent,sizeof(intent),&intent_size)||intent_size!=64||!equal(intent,o->manifest_sha,64))return invalid_receipt(__LINE__);
        } else if(nip_kind(path,0)!=0)return invalid_receipt(__LINE__);
    }
    return 1;
}
static int known_owned_installed(void) {
    if(nip_installed_kind()==0)return 1;
    if(nip_installed_kind()!=2)return 0;
    /* Only an earlier native installed_verified receipt confers ownership.
       Match its complete immutable stage again against installed bytes. */
    for(unsigned i=0;i<64;i++) {
        char name[64],path[192],final[NI_MAX_BODY+1];
        size_t n;
        int r=nip_list("attempts",i,name);
        if(r<0)return 0;
        if(!r)break;
        if(!hex(name,32)||!path_op(path,name,"final.json")||record_read(path,final,sizeof(final),&n))continue;
        Operation previous;
        if(!claim_read(name,&previous)||!final_parse(final,n,&previous)||R_STRCMP(previous.state,"installed_verified")||load_stage(previous.stage,&scratch)||R_STRCMP(scratch.sha,previous.manifest_sha))continue;
        if(verify_installed(&scratch))return 1;
    }
    return 0;
}
static int stage_reply(const Manifest *m,char *out,size_t cap) {
    int n=R_SNPRINTF(out,cap,"{\"app\":\"Vita Native Lifecycle\",\"protocol\":1,\"stage_attempt\":\"%s\",\"manifest_sha256\":\"%s\",\"manifest\":%s,\"files\":[",m->attempt,m->sha,m->raw);
    if(n<0||(size_t)n>=cap)return -1;
    size_t used=(size_t)n;
    int complete=1;
    for(unsigned i=0;i<NI_FILE_COUNT;i++) {
        char path[192];
        uint64_t bytes=0;
        int published=file_path(path,m,i,0)&&nip_kind(path,&bytes)==1;
        int verified=published&&bytes==m->files[i].bytes&&verify_file(m,i,0)==0;
        complete=complete&&verified;
        n=R_SNPRINTF(out+used,cap-used,"%s{\"index\":%u,\"published\":%s,\"verified\":%s}",i?",":"",i,published?"true":"false",verified?"true":"false");
        if(n<0||(size_t)n>=cap-used)return -1;
        used+=(size_t)n;
    }
    n=R_SNPRINTF(out+used,cap-used,"],\"complete\":%s,\"snapshot_atomic\":false}",complete?"true":"false");
    return n>0&&(size_t)n<cap-used?(int)(used+(size_t)n):-1;
}
static int failure(char *out,size_t cap,int status,const char *reason) {
    int n=R_SNPRINTF(out,cap,"{\"app\":\"Vita Native Lifecycle\",\"protocol\":1,\"error\":\"%s\"}",reason);
    if(n<0||(size_t)n>=cap){if(cap)out[0]=0;
        return 500;
        }return status;
}
void ni_init(void) {
    initialized=1;
    blocked=0;
    R_MEMSET(&active,0,sizeof(active));
    R_MEMSET(instance,0,sizeof(instance));
    if(!hex(R_BUILD_ID,64)||!lb_native_instance(instance)||nip_init()||nip_mkdir("stages")<0||nip_mkdir("attempts")<0){blocked=1;
        return;
        }
    if(count_entries("stages",32)<0||count_entries("attempts",64)<0){blocked=1;
        return;
        }
    for(unsigned i=0;i<64;i++) {
        char name[64],path[192],data[NI_MAX_BODY+1];
        size_t n;
        int r=nip_list("attempts",i,name);
        if(!r)break;
        Operation previous;
        if(r<0||!hex(name,32)||!claim_read(name,&previous)||!path_op(path,name,"final.json")||record_read(path,data,sizeof(data),&n)||!final_parse(data,n,&previous)) {blocked=1;
            continue;
            }
        if(!R_STRCMP(previous.state,"unknown"))blocked=1;
    }
}
int ni_request(int admin,const char *method,const char *path,const void *body,size_t size,char *out,size_t cap,NIDeferred *deferred) {
    if(deferred)R_MEMSET(deferred,0,sizeof(*deferred));
    if(!path||R_STRNCMP(path,"/native-lifecycle",17))return 0;
    if(!admin)return failure(out,cap,403,"administrator_required");
    if(!initialized)return failure(out,cap,503,"not_initialized");
    if(!method||!out||!cap||size>NI_MAX_BODY)return failure(out,cap,400,"request_invalid");
    if(!R_STRCMP(path,"/native-lifecycle/status")) {
        if(R_STRCMP(method,"GET")||size)return failure(out,cap,400,"method_or_body_invalid");
        char guard[NL_POLICY_REPLY_MAX];
        int paf_result=0,promoter_result=0;
        int installer_ready=nip_promote_available(&paf_result,&promoter_result);
        if(nl_policy_status(guard,sizeof(guard))<0)return failure(out,cap,503,"policy_unavailable");
        int n=R_SNPRINTF(out,cap,"{\"app\":\"Vita Native Lifecycle\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"project\":\"" NI_PROJECT "\",\"title_id\":\"" NI_TITLE "\",\"clock_ms\":%llu,\"blocked\":%s,\"active_attempt\":%s%s%s,\"policy\":\"conservative_idle_only\",\"max_file_bytes\":%u,\"max_total_bytes\":%u,\"installer\":{\"paf_result\":%d,\"promoter_result\":%d,\"ready\":%s},\"guard\":%s}",R_BUILD_ID,instance,(unsigned long long)r_pair_mono(),blocked?"true":"false",busy()?"\"":"",busy()?active.attempt:"null",busy()?"\"":"",NI_MAX_FILE,NI_MAX_TOTAL,paf_result,promoter_result,installer_ready?"true":"false",guard);
        return n>0&&(size_t)n<cap?200:failure(out,cap,500,"reply_too_large");
    }
    if(!R_STRCMP(path,"/native-lifecycle/stage")) {
        if(R_STRCMP(method,"POST")||!manifest_parse(body,size,&scratch))return failure(out,cap,400,"manifest_invalid");
        if(blocked||busy())return failure(out,cap,409,"service_blocked_or_busy");
        if(R_STRCMP(scratch.resident,R_BUILD_ID)||R_STRCMP(scratch.instance,instance))return failure(out,cap,409,"identity_mismatch");
        if(scratch.issued>UINT64_MAX-scratch.ttl||!fresh(scratch.issued,scratch.issued+scratch.ttl))return failure(out,cap,408,"request_expired");
        int entries=count_entries("stages",32);
        if(entries<0||entries>=32)return failure(out,cap,507,"stage_capacity");
        uint64_t space=0;
        if(nip_free(&space)<0||space<scratch.total*3+4*1024*1024)return failure(out,cap,507,"free_space_unavailable");
        char directory[192];
        path_stage(directory,scratch.attempt,"");
        if(nip_kind(directory,0)!=0||nip_mkdir(directory)!=0)return failure(out,cap,409,"stage_exists_or_uncertain");
        const char *dirs[]={"package","package/sce_sys","package/sce_sys/livearea","package/sce_sys/livearea/contents","package/sce_sys/package"};
        for(unsigned i=0;i<5;i++){path_stage(directory,scratch.attempt,dirs[i]);
            if(nip_mkdir(directory)!=0)return failure(out,cap,507,"stage_directory_failed");
            }
        path_stage(directory,scratch.attempt,"manifest.json");
        if(record_write(directory,body,size))return failure(out,cap,507,"manifest_storage_uncertain");
        return stage_reply(&scratch,out,cap)>0?201:failure(out,cap,500,"reply_too_large");
    }
    const char *stage_prefix="/native-lifecycle/stage/";
    size_t prefix=R_STRLEN(stage_prefix);
    if(!R_STRNCMP(path,stage_prefix,prefix)) {
        const char *tail=path+prefix;
        char id[33];
        if(R_STRLEN(tail)<32)return failure(out,cap,400,"path_invalid");
        R_MEMCPY(id,tail,32);
        id[32]=0;
        if(!hex(id,32))return failure(out,cap,400,"path_invalid");
        tail+=32;
        if(!*tail) {
            if(R_STRCMP(method,"GET")||size)return failure(out,cap,400,"method_or_body_invalid");
            if(load_stage(id,&scratch))return failure(out,cap,404,"stage_missing_or_invalid");
            return stage_reply(&scratch,out,cap)>0?200:failure(out,cap,500,"reply_too_large");
        }
        int install=!R_STRCMP(tail,"/install"),launch=!R_STRCMP(tail,"/launch");
        if(!install&&!launch)return failure(out,cap,400,"path_invalid");
        Operation next;
        if(R_STRCMP(method,"POST")||!operation_parse(body,size,&next))return failure(out,cap,400,"operation_invalid");
        if(blocked||busy())return failure(out,cap,409,"service_blocked_or_busy");
        if(R_STRCMP(next.resident,R_BUILD_ID)||R_STRCMP(next.instance,instance))return failure(out,cap,409,"identity_mismatch");
        if(!fresh(next.issued,next.expires))return failure(out,cap,408,"request_expired");
        if(load_stage(id,&next.candidate)||R_STRCMP(next.candidate.sha,next.manifest_sha)||R_STRCMP(next.candidate.instance,instance))return failure(out,cap,409,"manifest_or_stage_identity_mismatch");
        if(nl_idle_policy(NI_TITLE,1)!=0)return failure(out,cap,409,"native_idle_policy_refused");
        if(!verify_candidate(&next.candidate))return failure(out,cap,422,"candidate_verification_failed");
        if(install&&!known_owned_installed())return failure(out,cap,409,"installed_title_not_verified_owned");
        if(launch&&!verify_installed(&next.candidate))return failure(out,cap,409,"installed_candidate_mismatch");
        uint64_t space=0;
        if(install&&(nip_free(&space)<0||space<next.candidate.total*2+4*1024*1024))return failure(out,cap,507,"free_space_unavailable");
        int entries=count_entries("attempts",64);
        if(entries<0||entries>=64)return failure(out,cap,507,"attempt_capacity");
        char directory[192],claim[NI_MAX_BODY+1];
        path_op(directory,next.attempt,"");
        if(nip_kind(directory,0)!=0||nip_mkdir(directory)!=0)return failure(out,cap,409,"attempt_exists_or_uncertain");
        R_MEMCPY(next.stage,id,33);
        R_SNPRINTF(next.kind,sizeof(next.kind),"%s",install?"install":"launch");
        R_SNPRINTF(next.state,sizeof(next.state),"queued");
        next.present=1;
        int n=R_SNPRINTF(claim,sizeof(claim),"%s\n%s\n%s",id,next.kind,next.raw);
        path_op(directory,next.attempt,"claim.json");
        if(n<=0||(unsigned)n>=sizeof(claim)||record_write(directory,claim,(size_t)n)){blocked=1;
            return failure(out,cap,507,"claim_storage_uncertain");
            }
        active=next;
        if(deferred)R_MEMCPY(deferred->attempt,next.attempt,33);
        return receipt(out,cap,&active)>0?202:failure(out,cap,500,"reply_too_large");
    }
    const char *attempt_prefix="/native-lifecycle/attempt/";
    prefix=R_STRLEN(attempt_prefix);
    if(!R_STRNCMP(path,attempt_prefix,prefix)) {
        const char *id=path+prefix;
        if(!hex(id,32)||R_STRCMP(method,"GET")||size)return failure(out,cap,400,"path_or_body_invalid");
        if(active.present&&!R_STRCMP(id,active.attempt))return receipt(out,cap,&active)>0?200:failure(out,cap,500,"reply_too_large");
        Operation previous;
        if(!claim_read(id,&previous))return failure(out,cap,404,"attempt_missing_or_invalid");
        char record[192];
        size_t n=0;
        path_op(record,id,"final.json");
        if(record_read(record,out,cap,&n)||!final_parse(out,n,&previous)) {blocked=1;
            R_SNPRINTF(previous.state,sizeof(previous.state),"unknown");
            path_op(record,id,"intent");
            previous.dispatch=nip_kind(record,0)==1?1u:0u;
            return receipt(out,cap,&previous)>0?200:failure(out,cap,500,"reply_too_large");
            }
        return 200;
    }
    return failure(out,cap,400,"path_invalid");
}
int ni_upload(int admin,const char *method,const char *path,uint64_t length,const char *digest,NIRead reader,void *ctx,char *out,size_t cap) {
    if(!path||R_STRNCMP(path,"/native-lifecycle",17))return 0;
    if(!admin)return failure(out,cap,403,"administrator_required");
    const char *prefix="/native-lifecycle/stage/";
    size_t p=R_STRLEN(prefix);
    if(!method||R_STRCMP(method,"PUT")||R_STRNCMP(path,prefix,p)||R_STRLEN(path)!=p+32+8||!reader||!hex(digest,64))return failure(out,cap,400,"upload_path_or_digest_invalid");
    char id[33];
    R_MEMCPY(id,path+p,32);
    id[32]=0;
    const char *tail=path+p+32;
    if(!hex(id,32)||R_STRNCMP(tail,"/files/",7)||tail[7]<'0'||tail[7]>'7')return failure(out,cap,400,"upload_path_invalid");
    unsigned index=(unsigned)(tail[7]-'0');
    if(!initialized||blocked||busy())return failure(out,cap,409,"service_blocked_or_busy");
    if(load_stage(id,&scratch))return failure(out,cap,404,"stage_missing_or_invalid");
    if(R_STRCMP(scratch.instance,instance)||length!=scratch.files[index].bytes||!length||length>NI_MAX_FILE||R_STRCMP(digest,scratch.files[index].sha))return failure(out,cap,409,"upload_identity_mismatch");
    char part[192],final[192];
    file_path(part,&scratch,index,1);
    file_path(final,&scratch,index,0);
    if(nip_kind(part,0)!=0||nip_kind(final,0)!=0)return failure(out,cap,409,"file_exists_or_uncertain");
    int fd=nip_open_new(part);
    if(fd<0)return failure(out,cap,507,"file_create_failed");
    uint64_t total=0,deadline=r_pair_mono()+30000;
    int good=1;
    RSha h;
    rs_init(&h);
    while(total<length) {
        if(r_pair_mono()>=deadline){good=0;
            break;
            }
        size_t ask=length-total<sizeof(chunk)?(size_t)(length-total):sizeof(chunk);
        int n=reader(ctx,chunk,ask);
        if(n<=0||(size_t)n>ask){good=0;
            break;
            }
        size_t used=0;
        while(used<(size_t)n){int w=nip_write(fd,chunk+used,(size_t)n-used);
            if(w<=0||(size_t)w>(size_t)n-used){good=0;
                break;
                }used+=(size_t)w;
            }
        if(!good)break;
        rs_update(&h,chunk,(size_t)n);
        total+=(unsigned)n;
    }
    char observed[65];
    rs_final(&h,observed);
    if(total!=length||R_STRCMP(observed,digest))good=0;
    if(good&&nip_sync(fd)<0)good=0;
    if(nip_close(fd)<0)good=0;
    if(good&&nip_sync_device()<0)good=0;
    fd=good?nip_open_read(part):-1;
    if(good&&(fd<0||file_hash(fd,length,digest,index==0?scratch.build:0)))good=0;
    if(!good)return failure(out,cap,422,"file_upload_uncertain_retained_part");
    if(nip_rename_new(part,final)<0||nip_sync_device()<0||verify_file(&scratch,index,0))return failure(out,cap,507,"file_publication_uncertain");
    return stage_reply(&scratch,out,cap)>0?201:failure(out,cap,500,"reply_too_large");
}
void ni_after_response(const NIDeferred *deferred,int complete) {
    if(!deferred||!active.present||R_STRCMP(deferred->attempt,active.attempt)||R_STRCMP(active.state,"queued"))return;
    if(!complete){terminal("unknown");
        return;
        }
    if(!fresh(active.issued,active.expires)){terminal("expired");
        return;
        }
    if(nl_idle_policy(NI_TITLE,1)!=0||!verify_candidate(&active.candidate)){terminal("refused");
        return;
        }
    if((!R_STRCMP(active.kind,"install")&&!known_owned_installed())||(!R_STRCMP(active.kind,"launch")&&!verify_installed(&active.candidate))){terminal("refused");
        return;
        }
    char path[192],promotion[192]={0};
    if(!R_STRCMP(active.kind,"install")&&!promotion_copy(&active.candidate,active.attempt,promotion)){terminal("refused");
        return;
        }
    path_op(path,active.attempt,"intent");
    if(record_write(path,active.manifest_sha,64)){blocked=1;
        terminal("unknown");
        return;
        }
    active.dispatch=1;
    R_SNPRINTF(active.state,sizeof(active.state),"dispatch_intent");
    if(!fresh(active.issued,active.expires)){terminal("expired");
        return;
        }
    if(nl_idle_policy(NI_TITLE,1)!=0){terminal("refused");
        return;
        }
    if(!R_STRCMP(active.kind,"launch")) {
        NLLaunchResult result=nl_launch_owned_result(NI_TITLE,active.candidate.build);
        active.invoked=result.native_invoked;
        active.native_result=result.result;
        active.operation_result=result.result;
        terminal(!result.native_invoked?"refused":result.result<0?"native_rejected":"submitted");
        return;
    }
    int invoked=0;
    active.native_result=nip_promote_start(promotion,active.issued,active.expires,&invoked,&active.cleanup_result);
    active.invoked=invoked;
    if(active.native_result<0){terminal(invoked||active.cleanup_result<0?"unknown":"refused");
        return;
        }
    active.started=r_pair_mono();
    R_SNPRINTF(active.state,sizeof(active.state),"running");
}
void ni_tick(void) {
    if(!active.present||R_STRCMP(active.state,"running"))return;
    if(r_pair_mono()<active.started||r_pair_mono()-active.started>=60000){terminal("unknown");
        return;
        }
    int state=-1,result=-1;
    if(nip_promote_poll(&state,&result)<0){terminal("unknown");
        return;
        }
    if(state)return;
    active.operation_result=result;
    active.cleanup_result=nip_promote_finish();
    if(active.cleanup_result<0){terminal("unknown");
        return;
        }
    if(result<0){terminal("native_rejected");
        return;
        }
    if(result!=0||!verify_installed(&active.candidate)){terminal("unknown");
        return;
        }
    active.installed=1;
    terminal("installed_verified");
}
