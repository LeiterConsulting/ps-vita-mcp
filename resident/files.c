#include "files.h"
#include "files_platform.h"
#include "sha256.h"

typedef struct { char attempt[33],leaf[24]; unsigned offset,length; int operation; } RFPath;
static uint64_t deadline_ms;
static int expired(void) { return !r_running()||r_now()>=deadline_ms; }
static int lower_hex(const char *s) {
    if(R_STRLEN(s)!=32)return 0;
    for(unsigned i=0;i<32;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return 1;
}
static int leaf_ok(const char *s) {
    return !R_STRCMP(s,"package.vpk")||!R_STRCMP(s,"probe.bin")||
           !R_STRCMP(s,"package.vpk.part")||!R_STRCMP(s,"probe.bin.part");
}
static int decimal(const char **text,unsigned maximum,unsigned *value) {
    const char *p=*text,*first=p;unsigned n=0;
    if(*p<'0'||*p>'9')return 0;
    while(*p>='0'&&*p<='9') {
        unsigned digit=(unsigned)(*p-'0');
        if(n>maximum/10||(n==maximum/10&&digit>maximum%10))return 0;
        n=n*10+digit;p++;
    }
    if(p-first>1&&*first=='0')return 0;
    *text=p;*value=n;return 1;
}
static int parse(const char *path,RFPath *out) {
    R_MEMSET(out,0,sizeof(*out));const char *p;
    if(!R_STRNCMP(path,"/storage/list",13)) {
        out->operation=1;p=path+13;
        if(*p=='/') {
            p++;if(R_STRLEN(p)<32)return 0;
            R_MEMCPY(out->attempt,p,32);out->attempt[32]=0;p+=32;
            if(!lower_hex(out->attempt))return 0;
        }
        if(R_STRNCMP(p,"?offset=",8))return 0;
        p+=8;
        return decimal(&p,RF_OFFSET_MAX,&out->offset)&&!*p;
    }
    if(!R_STRNCMP(path,"/storage/stat/",14)) {out->operation=2;p=path+14;}
    else if(!R_STRNCMP(path,"/storage/read/",14)) {out->operation=3;p=path+14;}
    else return 0;
    if(R_STRLEN(p)<33)return 0;
    R_MEMCPY(out->attempt,p,32);out->attempt[32]=0;p+=32;
    if(!lower_hex(out->attempt)||*p++!='/')return 0;
    unsigned used=0;
    while(*p&&*p!='?'&&used<sizeof(out->leaf)-1)out->leaf[used++]=*p++;
    out->leaf[used]=0;if(!leaf_ok(out->leaf))return 0;
    if(out->operation==2)return !*p;
    if(R_STRNCMP(p,"?offset=",8))return 0;
    p+=8;
    if(!decimal(&p,R_MAX_FILE,&out->offset)||R_STRNCMP(p,"&length=",8))return 0;
    p+=8;
    return decimal(&p,RF_READ_MAX,&out->length)&&out->length&&!*p;
}
static void fail(char *json,size_t capacity,RFResult *out,int code,const char *reason) {
    int n=R_SNPRINTF(json,capacity,"{\"error\":\"%s\"}",reason);
    out->status=code;out->binary=0;out->length=n>0&&(size_t)n<capacity?(size_t)n:0;
}
static int append(char *json,size_t capacity,size_t *used,const char *text) {
    size_t n=R_STRLEN(text);if(n>=capacity-*used)return 0;
    R_MEMCPY(json+*used,text,n+1);*used+=n;return 1;
}
static void listing(const RFPath *p,char *json,size_t capacity,RFResult *out) {
    int dir=rf_dir_open(p->attempt[0]?p->attempt:0);
    if(dir<0) {fail(json,capacity,out,dir==-2?500:404,"Managed directory unavailable");return;}
    RFEntry entry;unsigned skipped=0,scanned=0,accepted=0;int code=0,more=0,good=1;
    while(skipped<p->offset&&!expired()) {
        code=rf_dir_next(dir,&entry);if(code<=0)break;skipped++;
    }
    char attempt[40];
    if(p->attempt[0])R_SNPRINTF(attempt,sizeof(attempt),"\"%s\"",p->attempt);
    else R_MEMCPY(attempt,"null",5);
    int n=R_SNPRINTF(json,capacity,"{\"app\":\"Vita Resident\",\"protocol\":1,\"storage_protocol\":1,\"operation\":\"list\",\"attempt\":%s,\"offset\":%u,\"snapshot\":false,\"entries\":[",attempt,p->offset);
    size_t used=n>0&&(size_t)n<capacity?(size_t)n:0;if(!used)good=0;
    while(good&&skipped==p->offset&&scanned<RF_PAGE&&!expired()) {
        code=rf_dir_next(dir,&entry);if(code<=0)break;scanned++;
        int allowed=p->attempt[0]?(entry.kind==1&&leaf_ok(entry.name)&&entry.bytes<=R_MAX_FILE):
                                     (entry.kind==2&&lower_hex(entry.name));
        if(!allowed)continue;
        char text[160];
        if(entry.kind==1)n=R_SNPRINTF(text,sizeof(text),"%s{\"name\":\"%s\",\"kind\":\"file\",\"bytes\":%llu}",accepted?",":"",entry.name,(unsigned long long)entry.bytes);
        else n=R_SNPRINTF(text,sizeof(text),"%s{\"name\":\"%s\",\"kind\":\"directory\"}",accepted?",":"",entry.name);
        if(n<=0||(size_t)n>=sizeof(text)||!append(json,capacity,&used,text))good=0;
        accepted++;
    }
    if(good&&code>=0&&skipped==p->offset&&scanned==RF_PAGE&&!expired()) {
        code=rf_dir_next(dir,&entry);if(code>0)more=1;
    }
    if(rf_dir_close(dir)<0)good=0;
    if(expired()) {fail(json,capacity,out,408,"Managed inspection deadline exceeded");return;}
    if(!good||code<0) {fail(json,capacity,out,500,"Managed directory read failed");return;}
    unsigned next=p->offset+scanned;int limit=more&&next>RF_OFFSET_MAX;char cursor[16];
    if(more&&!limit)R_SNPRINTF(cursor,sizeof(cursor),"%u",next);else R_MEMCPY(cursor,"null",5);
    char tail[160];n=R_SNPRINTF(tail,sizeof(tail),"],\"next_offset\":%s,\"has_more\":%s,\"limit_reached\":%s}",cursor,more?"true":"false",limit?"true":"false");
    if(n<=0||(size_t)n>=sizeof(tail)||!append(json,capacity,&used,tail)) {fail(json,capacity,out,500,"Managed directory read failed");return;}
    out->status=200;out->binary=0;out->length=used;
}
static void file(const RFPath *p,char *json,size_t capacity,unsigned char *data,size_t data_capacity,RFResult *out) {
    uint64_t size=0,after=0;int fd=rf_open(p->attempt,p->leaf,&size);
    if(fd<0) {fail(json,capacity,out,fd==-2?500:404,"Managed regular file unavailable");return;}
    int good=1;unsigned count=0;char digest[65]={0};
    if(p->operation==2) {
        RSha sha;rs_init(&sha);
        while((uint64_t)count<size&&!expired()) {
            size_t wanted=size-count>data_capacity?data_capacity:(size_t)(size-count);
            int n=r_read(fd,data,wanted);
            if(n<=0||(size_t)n>wanted) {good=0;break;}
            count+=(unsigned)n;rs_update(&sha,data,(size_t)n);
        }
        rs_final(&sha,digest);
    } else if(p->offset>size) {
        rf_close(fd);fail(json,capacity,out,416,"Managed read offset exceeds file");return;
    } else {
        unsigned wanted=size-p->offset>p->length?p->length:(unsigned)(size-p->offset);
        if(wanted>data_capacity||rf_seek(fd,p->offset)<0)good=0;
        while(good&&count<wanted&&!expired()) {
            int n=r_read(fd,data+count,wanted-count);
            if(n<=0||(unsigned)n>wanted-count) {good=0;break;}
            count+=(unsigned)n;
        }
        if(count!=wanted)good=0;
    }
    if(rf_size(fd,&after)<0||after!=size)good=0;
    if(rf_close(fd)<0)good=0;
    if(expired()) {fail(json,capacity,out,408,"Managed inspection deadline exceeded");return;}
    if(!good||(p->operation==2&&count!=size)) {fail(json,capacity,out,500,"Managed file read failed or changed");return;}
    if(p->operation==3) {out->status=200;out->binary=1;out->length=count;return;}
    int n=R_SNPRINTF(json,capacity,"{\"app\":\"Vita Resident\",\"protocol\":1,\"storage_protocol\":1,\"operation\":\"stat\",\"attempt\":\"%s\",\"file\":\"%s\",\"bytes\":%llu,\"sha256\":\"%s\",\"snapshot\":false}",p->attempt,p->leaf,(unsigned long long)size,digest);
    if(n<=0||(size_t)n>=capacity) {fail(json,capacity,out,500,"Managed file read failed or changed");return;}
    out->status=200;out->binary=0;out->length=(size_t)n;
}
void rf_request(const char *path,char *json,size_t capacity,unsigned char *data,
                size_t data_capacity,uint64_t deadline,RFResult *out) {
    deadline_ms=deadline;R_MEMSET(out,0,sizeof(*out));RFPath parsed;
    if(!parse(path,&parsed)) {fail(json,capacity,out,400,"Invalid managed inspection path");return;}
    if(!data_capacity) {fail(json,capacity,out,500,"Managed file read failed or changed");return;}
    if(parsed.operation==1)listing(&parsed,json,capacity,out);
    else file(&parsed,json,capacity,data,data_capacity,out);
}
