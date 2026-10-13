#include "lab_core.h"
#include <stdio.h>
#include <string.h>
#include <limits.h>

static uint32_t selftest(void) {
    /* Standard CRC-32/ISO-HDLC of bytes(range(256))*16. Independent expected
       vector is 0xa2912082, recorded in the host/build acceptance report. */
    uint32_t crc=UINT32_MAX;
    for(unsigned n=0;n<4096;n++) {
        crc^=(n&255u);
        for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^((0u-(crc&1u))&UINT32_C(0xedb88320));
    }
    return crc^UINT32_MAX;
}
static int hex(const char *text,unsigned bytes) {
    if(!text||strlen(text)!=bytes)return 0;
    for(unsigned n=0;n<bytes;n++)
        if(!((text[n]>='0'&&text[n]<='9')||(text[n]>='a'&&text[n]<='f')))return 0;
    return 1;
}
int lab_init(LabCore *c,int32_t pid,const unsigned char nonce[16]) {
    if(!c||!nonce||pid<=0||!hex(LAB_BUILD_ID,64))return 0;
    memset(c,0,sizeof(*c));unsigned nonzero=0;
    static const char digits[]="0123456789abcdef";
    for(unsigned n=0;n<16;n++){nonzero|=nonce[n];c->run[2*n]=digits[nonce[n]>>4];c->run[2*n+1]=digits[nonce[n]&15];}
    if(!nonzero){memset(c,0,sizeof(*c));return 0;}
    c->pid=pid;c->revision=1;c->checksum=selftest();
    c->selftest_passed=c->checksum==UINT32_C(0xa2912082);return 1;
}
void lab_tick(LabCore *c,uint64_t now) { c->frame++;c->sampled_ms=now; }
int lab_status(const LabCore *c,char *out,size_t cap,int acknowledged) {
    if(!c||!out||!cap)return -1;
    int n=snprintf(out,cap,
        "{\"app\":\"" LAB_APP "\",\"protocol\":1,\"title_id\":\"" LAB_TITLE "\","
        "\"version\":\"" LAB_VERSION "\",\"native_build_id\":\"" LAB_BUILD_ID "\","
        "\"pid\":%d,\"run\":\"%s\",\"revision\":%u,\"frame\":%llu,\"sampled_ms\":%llu,"
        "\"paused\":true,\"selftest_passed\":%s,\"checksum\":%u,\"variant\":%u,"
        "\"exiting\":%s,\"exit_expected_revision\":%u,\"exit_response_complete\":%s%s}",
        (int)c->pid,c->run,c->revision,(unsigned long long)c->frame,(unsigned long long)c->sampled_ms,
        c->selftest_passed?"true":"false",c->checksum,(unsigned)LAB_VARIANT,
        c->exit_phase?"true":"false",c->exit_expected_revision,
        c->exit_response_complete?"true":"false",acknowledged?",\"exit_response\":\"acknowledged\"":"");
    if(n<0||(size_t)n>=cap){out[0]=0;return -1;}return n;
}
typedef struct { const unsigned char *p,*end; } Json;
static void spaces(Json *j){while(j->p<j->end&&(*j->p==' '||*j->p=='\t'||*j->p=='\r'||*j->p=='\n'))j->p++;}
static int take(Json *j,unsigned char ch){spaces(j);if(j->p==j->end||*j->p!=ch)return 0;j->p++;return 1;}
static int string(Json *j,char *out,size_t cap) {
    if(!take(j,'"'))return 0;
    size_t n=0;
    while(j->p<j->end){unsigned char ch=*j->p++;if(ch=='"'){out[n]=0;return 1;}
        if(ch<32||ch>126||ch=='\\'||n+1>=cap)return 0;
        out[n++]=(char)ch;}
    return 0;
}
static int number(Json *j,uint32_t *out) {
    spaces(j);if(j->p==j->end||*j->p<'0'||*j->p>'9')return 0;
    if(*j->p=='0'){j->p++;*out=0;return j->p==j->end||*j->p<'0'||*j->p>'9';}
    uint32_t n=0;
    while(j->p<j->end&&*j->p>='0'&&*j->p<='9'){
        unsigned digit=*j->p++-'0';if(n>(UINT32_MAX-digit)/10)return 0;n=n*10+digit;}
    *out=n;return 1;
}
int lab_offer_exit(LabCore *c,const char *body,size_t bytes) {
    if(!c||!body||!bytes||bytes>511||memchr(body,0,bytes))return 400;
    Json j={(const unsigned char *)body,(const unsigned char *)body+bytes};
    char run[33]={0},build[65]={0};uint32_t pid=0,revision=0;unsigned seen=0;
    if(!take(&j,'{'))return 400;
    for(unsigned n=0;n<4;n++){
        char key[40];if(n&&!take(&j,','))return 400;
        if(!string(&j,key,sizeof(key))||!take(&j,':'))return 400;
        static const char *const fields[]={"expected_native_build_id","expected_pid","expected_run","expected_revision"};
        unsigned field;for(field=0;field<4;field++)if(!strcmp(key,fields[field]))break;
        if(field==4||(seen&(1u<<field)))return 400;
        seen|=1u<<field;
        if(field==0){if(!string(&j,build,sizeof(build))||!hex(build,64))return 400;}
        else if(field==1){if(!number(&j,&pid)||!pid||pid>INT32_MAX)return 400;}
        else if(field==2){if(!string(&j,run,sizeof(run))||!hex(run,32))return 400;}
        else if(!number(&j,&revision)||!revision)return 400;
    }
    if(seen!=15||!take(&j,'}'))return 400;
    spaces(&j);if(j.p!=j.end)return 400;
    if(strcmp(build,LAB_BUILD_ID)||strcmp(run,c->run)||pid!=(uint32_t)c->pid||revision!=c->revision)return 412;
    if(c->exit_phase||!c->frame||c->revision==UINT32_MAX)return 409;
    c->exit_expected_revision=c->revision;c->revision++;
    c->exit_phase=1;c->exit_response_complete=0;return 200;
}
void lab_finish_exit(LabCore *c,int complete,int closed) {
    if(c->exit_phase!=1)return;
    c->exit_response_complete=complete==1&&closed==1;
    c->exit_phase=c->exit_response_complete?2:0;
}
int lab_exit_ready(const LabCore *c){return c&&c->exit_phase==2;}
