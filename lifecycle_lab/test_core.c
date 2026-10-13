#include "lab_core.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned checks;
static void check(int value){assert(value);checks++;}
static void body(const LabCore *c,char out[512],const char *build,const char *run,uint32_t pid,uint32_t revision){
    (void)c;snprintf(out,512,"{\"expected_native_build_id\":\"%s\",\"expected_pid\":%u,\"expected_run\":\"%s\",\"expected_revision\":%u}",build,pid,run,revision);
}
int main(void){
    LabCore c;unsigned char zero[16]={0},nonce[16]={1,2,3};
    check(!lab_init(&c,77,zero));check(!lab_init(&c,0,nonce));check(lab_init(&c,77,nonce));
    check(c.selftest_passed&&c.checksum==UINT32_C(0xa2912082)&&c.revision==1&&!c.frame);
    check(!strcmp(c.run,"01020300000000000000000000000000"));lab_tick(&c,1000);check(c.frame==1&&c.sampled_ms==1000);
    char text[512],json[LAB_JSON_MAX];body(&c,text,LAB_BUILD_ID,c.run,77,1);
    check(lab_status(&c,json,sizeof(json),0)>0&&strstr(json,"\"paused\":true"));
    check(lab_status(&c,json,1,0)<0&&!json[0]);
    check(lab_offer_exit(&c,text,strlen(text))==200&&c.exit_phase==1&&c.revision==2&&c.exit_expected_revision==1);
    check(!lab_exit_ready(&c));check(lab_offer_exit(&c,text,strlen(text))==412);
    lab_finish_exit(&c,0,1);check(!lab_exit_ready(&c)&&!c.exit_phase&&!c.exit_response_complete&&c.revision==2);
    check(lab_offer_exit(&c,text,strlen(text))==412);
    body(&c,text,LAB_BUILD_ID,c.run,77,2);check(lab_offer_exit(&c,text,strlen(text))==200&&c.revision==3);
    lab_finish_exit(&c,1,0);check(!lab_exit_ready(&c)&&!c.exit_response_complete);
    body(&c,text,LAB_BUILD_ID,c.run,77,3);check(lab_offer_exit(&c,text,strlen(text))==200);
    lab_finish_exit(&c,1,1);check(lab_exit_ready(&c)&&c.exit_response_complete);
    check(lab_status(&c,json,sizeof(json),1)>0&&strstr(json,"\"exit_response\":\"acknowledged\""));
    check(lab_init(&c,77,nonce));lab_tick(&c,1000);
    body(&c,text,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",c.run,77,1);check(lab_offer_exit(&c,text,strlen(text))==412);
    body(&c,text,LAB_BUILD_ID,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",77,1);check(lab_offer_exit(&c,text,strlen(text))==412);
    body(&c,text,LAB_BUILD_ID,c.run,78,1);check(lab_offer_exit(&c,text,strlen(text))==412);
    body(&c,text,LAB_BUILD_ID,c.run,77,9);check(lab_offer_exit(&c,text,strlen(text))==412);
    const char *bad[]={"{}","{\"expected_pid\":true}","[]","null","{\"expected_pid\":01}","{\"expected_revision\":4294967296}"};
    for(unsigned n=0;n<sizeof(bad)/sizeof(bad[0]);n++)check(lab_offer_exit(&c,bad[n],strlen(bad[n]))==400&&c.revision==1);
    body(&c,text,LAB_BUILD_ID,c.run,77,1);strcat(text,"x");check(lab_offer_exit(&c,text,strlen(text))==400);
    text[strlen(text)-1]=0;text[50]=0;check(lab_offer_exit(&c,text,250)==400);
    c.selftest_passed=0;body(&c,text,LAB_BUILD_ID,c.run,78,1);check(lab_offer_exit(&c,text,strlen(text))==412);
    body(&c,text,LAB_BUILD_ID,c.run,77,1);check(lab_offer_exit(&c,text,strlen(text))==200);
    check(!lab_exit_ready(&c));lab_finish_exit(&c,1,1);check(lab_exit_ready(&c)&&c.exit_response_complete);
    printf("native lab protocol/exit: %u assertions passed; no Vita runtime acceptance\n",checks);return 0;
}
