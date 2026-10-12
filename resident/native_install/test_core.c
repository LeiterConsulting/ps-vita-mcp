#define _POSIX_C_SOURCE 200809L
#include "service.h"
#include "platform.h"
#include "paths.h"
#include "../platform.h"
#include "../sha256.h"
#include <stdlib.h>
#include <unistd.h>
#include <sys/stat.h>

static unsigned checks,cases;static uint64_t clock_ms=100000;static char root[1024],stage[33],manifest[4097],manifest_sha[65],reply[4096];
static const char build[]="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
static unsigned char files[8][2048];static size_t lengths[8];static char hashes[8][65];static unsigned next_id=1;
static NIDeferred deferred;
static void check(int passed,const char *expression,unsigned line) {
    checks++;
    if(!passed){fprintf(stderr,"FAIL %s:%u %s\nreply=%s\n",__FILE__,line,expression,reply);
        exit(1);
        }
}
#define CHECK(x) check((x),#x,__LINE__)
uint64_t r_pair_mono(void) {return clock_ms;
    }
int lb_native_instance(char out[33]) {memset(out,'b',32);
    out[32]=0;
    return 1;
    }
static void hash(const void *data,size_t n,char out[65]) {RSha h;
    rs_init(&h);
    rs_update(&h,data,n);
    rs_final(&h,out);
    }
static void p32(unsigned char *p,unsigned n) {for(unsigned i=0;i<4;i++)p[i]=(unsigned char)(n>>(8*i));
    }
static void fixture(void) {
    char pattern[]="/tmp/vita-native-install-XXXXXX";
    char *folder=mkdtemp(pattern);
    CHECK(folder!=NULL);
    snprintf(root,sizeof(root),"%s",folder);
    nip_host_root(root);
    char marker[1200];
    snprintf(marker,sizeof(marker),"%s/native-idle-ready",root);
    FILE *f=fopen(marker,"wb");
    CHECK(f!=NULL);
    CHECK(fclose(f)==0);
    ni_init();
    CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"blocked\":false")!=NULL);
    memset(files,0,sizeof(files));
    lengths[0]=1024;
    memcpy(files[0],"SCE\0",4);
    p32(files[0]+0x80,1);
    p32(files[0]+0x84,0x2f000000);
    snprintf((char *)files[0]+512,sizeof(files[0])-512,"VITA_NATIVE_LIFECYCLE_LAB:%s",build);
    const char *keys[]={"TITLE_ID","APP_VER","CATEGORY","PSP2_SYSTEM_VER"};
    const char *values[]={NI_TITLE,"01.00","gd",NULL};
    unsigned keypos=84,valuepos=160,offset=0;
    p32(files[1],0x46535000);
    p32(files[1]+4,0x101);
    p32(files[1]+8,keypos);
    p32(files[1]+12,valuepos);
    p32(files[1]+16,4);
    for(unsigned i=0;i<4;i++){unsigned char *e=files[1]+20+i*16;
        e[0]=(unsigned char)(keypos-84);
        e[2]=4;
        e[3]=i==3?4:2;
        unsigned n=i==3?4:(unsigned)strlen(values[i])+1;
        p32(e+4,n);
        p32(e+8,n);
        p32(e+12,offset);
        strcpy((char *)files[1]+keypos,keys[i]);
        keypos+=(unsigned)strlen(keys[i])+1;
        if(i==3)p32(files[1]+valuepos+offset,0x03650000);
        else memcpy(files[1]+valuepos+offset,values[i],n);
        offset+=n;
        }
    lengths[1]=valuepos+offset;
    for(unsigned i=2;i<7;i++){lengths[i]=32;
        memset(files[i],(int)i,lengths[i]);
        }
    lengths[7]=0x430;
    memcpy(files[7],"\x7fPKG",4);
    memcpy(files[7]+0x30,"EP9000-" NI_TITLE "_00-0000000000000000",36);
    for(unsigned i=0;i<8;i++)hash(files[i],lengths[i],hashes[i]);
    cases++;
}
static void make_manifest(void) {
    snprintf(stage,sizeof(stage),"%032x",next_id++);
    int n=snprintf(manifest,sizeof(manifest),"{\"protocol\":1,\"project\":\"" NI_PROJECT "\",\"title_id\":\"" NI_TITLE "\",\"version\":\"01.00\",\"native_build_id\":\"%s\",\"package_sha256\":\"%s\",\"package_bytes\":1234,\"resident_build_id\":\"%s\",\"instance_id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"attempt\":\"%s\",\"issued_ms\":%llu,\"ttl_ms\":30000,\"files\":[",build,build,R_BUILD_ID,stage,(unsigned long long)clock_ms);
    for(unsigned i=0;i<8;i++)n+=snprintf(manifest+n,sizeof(manifest)-(size_t)n,"%s{\"bytes\":%zu,\"sha256\":\"%s\"}",i?",":"",lengths[i],hashes[i]);
    snprintf(manifest+n,sizeof(manifest)-(size_t)n,"]}");
    hash(manifest,strlen(manifest),manifest_sha);
}
typedef struct {const unsigned char *data;
    size_t size,used;
    int short_stream;
    } Reader;
static int reader(void *ctx,void *out,size_t capacity) {Reader *r=ctx;
    if(r->short_stream&&r->used)return 0;
    size_t n=r->size-r->used;
    if(n>capacity)n=capacity;
    if(r->short_stream&&n>1)n=1;
    memcpy(out,r->data+r->used,n);
    r->used+=n;
    return (int)n;
    }
static int upload(unsigned index,int short_stream,const char *digest) {char path[128];
    snprintf(path,sizeof(path),"/native-lifecycle/stage/%s/files/%u",stage,index);
    Reader r={files[index],lengths[index],0,short_stream};
    return ni_upload(1,"PUT",path,lengths[index],digest?digest:hashes[index],reader,&r,reply,sizeof(reply));
    }
static void stage_all(void) {make_manifest();
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==201);
    for(unsigned i=0;i<8;i++)CHECK(upload(i,0,NULL)==201);
    CHECK(strstr(reply,"\"complete\":true")!=NULL);
    }
static int operation(const char *kind,char id[33]) {char body[1024],path[128];
    snprintf(id,33,"%032x",next_id++);
    snprintf(path,sizeof(path),"/native-lifecycle/stage/%s/%s",stage,kind);
    snprintf(body,sizeof(body),"{\"manifest_sha256\":\"%s\",\"resident_build_id\":\"%s\",\"instance_id\":\"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"issued_ms\":%llu,\"ttl_ms\":30000,\"attempt\":\"%s\"}",manifest_sha,R_BUILD_ID,(unsigned long long)clock_ms,id);
    return ni_request(1,"POST",path,body,strlen(body),reply,sizeof(reply),&deferred);
    }
static void get_operation(const char *id) {char path[128];
    snprintf(path,sizeof(path),"/native-lifecycle/attempt/%s",id);
    CHECK(ni_request(1,"GET",path,NULL,0,reply,sizeof(reply),&deferred)==200);
    }
static void dispatch(const char *id,int complete) {NIDeferred action;
    strcpy(action.attempt,id);
    ni_after_response(&action,complete);
    }
static void finish_install(const char *id) {dispatch(id,1);
    ni_tick();
    ni_tick();
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"installed_verified\"")!=NULL);
    CHECK(strstr(reply,"\"installed_verified\":true")!=NULL);
    }
static void success_cycle(void) {
    fixture();
    stage_all();
    char id[33];
    CHECK(operation("install",id)==202);
    unsigned before=nip_host_submissions();
    CHECK(strstr(reply,"\"dispatch_count\":0")!=NULL);
    CHECK(nip_host_submissions()==before);
    finish_install(id);
    CHECK(nip_host_submissions()==before+1);
    CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"active_attempt\":null")!=NULL);
    CHECK(operation("launch",id)==202);
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"submitted\"")!=NULL);
    CHECK(nip_host_submissions()==before+2);
    ni_init();
    CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"blocked\":false")!=NULL);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"submitted\"")!=NULL);
    CHECK(strstr(reply,"\"installed_verified\":false")!=NULL);
    CHECK(nip_host_submissions()==before+2);
    CHECK(operation("install",id)==202);
    finish_install(id);
    CHECK(nip_host_submissions()==before+3);
    ni_init();
    CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"blocked\":false")!=NULL);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"installed_verified\"")!=NULL);
    char path[128];
    snprintf(path,sizeof(path),"/native-lifecycle/stage/%s",stage);
    CHECK(ni_request(1,"GET",path,NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"complete\":true")!=NULL);
}
static void schema_and_upload(void) {
    fixture();
    make_manifest();
    CHECK(ni_request(0,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==403);
    char bad[4097];
    snprintf(bad,sizeof(bad),"{\"protocol\":1,%s",manifest+1);
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",bad,strlen(bad),reply,sizeof(reply),&deferred)==400);
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==201);
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==409);
    CHECK(upload(0,0,build)==409);
    CHECK(upload(0,1,NULL)==422);
    CHECK(upload(0,0,NULL)==409);
    CHECK(ni_request(1,"GET","/native-lifecycle/stage/../x",NULL,0,reply,sizeof(reply),&deferred)==400);
    CHECK(ni_request(1,"GET","/native-lifecycle/status","x",1,reply,sizeof(reply),&deferred)==400);
}
static void refusal_and_unknown(void) {
    char id[33];
    fixture();
    stage_all();
    unsigned before=nip_host_submissions();
    CHECK(operation("install",id)==202);
    dispatch(id,0);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    CHECK(nip_host_submissions()==before);
    CHECK(operation("install",id)==409);
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    clock_ms+=30001;
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"expired\"")!=NULL);
    CHECK(nip_host_submissions()==before);
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    ni_init();
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    CHECK(operation("install",id)==409);
    CHECK(nip_host_submissions()==before);
    fixture();
    stage_all();
    nip_host_fault("paf",1);
    CHECK(operation("install",id)==202);
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"refused\"")!=NULL);
    CHECK(nip_host_submissions()==before);
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    nip_host_fault("promoter-submit",1);
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    CHECK(nip_host_submissions()==before+1);
}
static void io_and_identity_faults(void) {
    char id[33],path[1200];
    fixture();
    make_manifest();
    nip_host_fault("sync",1);
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==507);
    CHECK(ni_request(1,"POST","/native-lifecycle/stage",manifest,strlen(manifest),reply,sizeof(reply),&deferred)==409);
    fixture();
    files[1][0]^=1;
    hash(files[1],lengths[1],hashes[1]);
    stage_all();
    CHECK(operation("install",id)==422);
    fixture();
    stage_all();
    snprintf(path,sizeof(path),"%s/native-installed",root);
    CHECK(mkdir(path,0700)==0);
    snprintf(path,sizeof(path),"%s/native-installed/" NI_TITLE,root);
    CHECK(mkdir(path,0700)==0);
    CHECK(operation("install",id)==409);
    fixture();
    stage_all();
    snprintf(path,sizeof(path),"%s/n1/%s/stages/%s/package/eboot.bin",root,R_BUILD_ID,stage);
    CHECK(unlink(path)==0);
    CHECK(symlink("/etc/passwd",path)==0);
    CHECK(operation("install",id)==422);
}
static void fault_marker(const char *name) {
    char path[1200];
    snprintf(path,sizeof(path),"%s/native-fault-%s",root,name);
    FILE *f=fopen(path,"wb");
    CHECK(f!=NULL);
    CHECK(fclose(f)==0);
}
static void promoter_faults(void) {
    const char *faults[]={"promoter-poll","promoter-result","promoter-cleanup","installed-corrupt"};
    const char *states[]={"unknown","native_rejected","unknown","unknown"};
    char id[33];
    for(unsigned i=0;i<4;i++) {
        fixture();
        stage_all();
        unsigned before=nip_host_submissions();
        CHECK(operation("install",id)==202);
        dispatch(id,1);
        nip_host_fault(faults[i],1);
        ni_tick();
        ni_tick();
        get_operation(id);
        char expected[80];
        snprintf(expected,sizeof(expected),"\"state\":\"%s\"",states[i]);
        CHECK(strstr(reply,expected)!=NULL);
        CHECK(strstr(reply,"\"native_invoked\":true")!=NULL);
        CHECK(nip_host_submissions()==before+1);
        ni_init();
        CHECK(nip_host_submissions()==before+1);
        CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
        CHECK(strstr(reply,i==1?"\"blocked\":false":"\"blocked\":true")!=NULL);
    }
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    unsigned before=nip_host_submissions();
    nip_host_fault("promoter-guard",1);
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"refused\"")!=NULL);
    CHECK(strstr(reply,"\"native_invoked\":false")!=NULL);
    CHECK(nip_host_submissions()==before);
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    fault_marker("promoter-guard");
    fault_marker("promoter-cleanup");
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    CHECK(strstr(reply,"\"native_invoked\":false")!=NULL);
    CHECK(strstr(reply,"\"cleanup_result\":-14004")!=NULL);
    CHECK(nip_host_submissions()==before);
    fixture();
    stage_all();
    CHECK(operation("install",id)==202);
    dispatch(id,1);
    clock_ms+=60001;
    ni_tick();
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    ni_init();
    CHECK(nip_host_submissions()==before+1);
}
static void consumed_working_copy(void) {
    fixture();
    stage_all();
    char id[33],path[128];
    CHECK(operation("install",id)==202);
    dispatch(id,1);
    nip_host_fault("promoter-consume",1);
    ni_tick();
    ni_tick();
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"installed_verified\"")!=NULL);
    snprintf(path,sizeof(path),"/native-lifecycle/stage/%s",stage);
    CHECK(ni_request(1,"GET",path,NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"complete\":true")!=NULL);
    CHECK(operation("launch",id)==202);
    dispatch(id,1);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"submitted\"")!=NULL);
}
static void recovery_receipt_binding(void) {
    fixture();
    stage_all();
    char id[33],path[1200];
    CHECK(operation("install",id)==202);
    finish_install(id);
    snprintf(path,sizeof(path),"%s/n1/%s/attempts/%s/final.json",root,R_BUILD_ID,id);
    FILE *f=fopen(path,"rb");
    CHECK(f!=NULL);
    char envelope[4096];
    size_t size=fread(envelope,1,sizeof(envelope)-1,f);
    CHECK(size>65&&size<sizeof(envelope)-1);
    CHECK(fclose(f)==0);
    envelope[size-65]=0;
    char *attempt=strstr(envelope,"\"attempt\":\"");
    CHECK(attempt!=NULL);
    attempt[strlen("\"attempt\":\"")]='f';
    char checksum[65];
    hash(envelope,size-65,checksum);
    envelope[size-65]='\n';
    memcpy(envelope+size-64,checksum,64);
    f=fopen(path,"wb");
    CHECK(f!=NULL);
    CHECK(fwrite(envelope,1,size,f)==size);
    CHECK(fclose(f)==0);
    unsigned before=nip_host_submissions();
    ni_init();
    CHECK(ni_request(1,"GET","/native-lifecycle/status",NULL,0,reply,sizeof(reply),&deferred)==200);
    CHECK(strstr(reply,"\"blocked\":true")!=NULL);
    get_operation(id);
    CHECK(strstr(reply,"\"state\":\"unknown\"")!=NULL);
    CHECK(operation("install",id)==409);
    CHECK(nip_host_submissions()==before);
}
static void vita_promotion_paths(void) {
    static const char *const names[]={
        "eboot.bin","sce_sys/param.sfo","sce_sys/icon0.png",
        "sce_sys/livearea/contents/bg.png","sce_sys/livearea/contents/startup.png",
        "sce_sys/livearea/contents/template.xml","LICENSE","sce_sys/package/head.bin"};
    const char *id="0123456789abcdef0123456789abcdef";
    char relative[192],absolute[384],expected[384];
    for(unsigned i=0;i<8;i++) {
        snprintf(relative,sizeof(relative),"p/%s/%s",id,names[i]);
        snprintf(expected,sizeof(expected),NI_PROMOTION_ROOT "/%s/%s",id,names[i]);
        CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,relative)==1);
        CHECK(strcmp(absolute,expected)==0);
        CHECK(strlen(absolute)<NI_PROMOTION_PATH_MAX);
    }
    snprintf(relative,sizeof(relative),"stages/%s/package/eboot.bin",id);
    snprintf(expected,sizeof(expected),NI_SCOPED_ROOT "/%s/%s",R_BUILD_ID,relative);
    CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,relative)==1);
    CHECK(strcmp(absolute,expected)==0);
    CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,"p")==1);
    CHECK(strcmp(absolute,NI_PROMOTION_ROOT)==0);
    CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,"p/../../ur0:tai/config.txt")==0);
    CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,"p/0123456789abcdef0123456789abcdefff/unregistered.bin")==0);
    CHECK(ni_vita_path(absolute,sizeof(absolute),R_BUILD_ID,"p/0123456789ABCDEF0123456789ABCDEFff/eboot.bin")==0);
    CHECK(ni_vita_path(absolute,8,R_BUILD_ID,"p")==0);
}
int main(void) {success_cycle();
    schema_and_upload();
    refusal_and_unknown();
    io_and_identity_faults();
    promoter_faults();
    consumed_working_copy();
    recovery_receipt_binding();
    vita_promotion_paths();
    printf("PASS native install core: %u fixtures, %u assertions; real POSIX persistence/streaming, simulated SDK effects\n",cases,checks);
    return 0;
    }
