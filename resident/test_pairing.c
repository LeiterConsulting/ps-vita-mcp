/* The real pairing state machine under deterministic clock/crypto/storage fixtures. */
#include "pairing.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static PRRegistry slots[2];
static int present[2], fail_store, fail_load, stores;
static uint64_t mono=1000, utc=1791144000;
static unsigned entropy=1;
static uint64_t clock_mono(void){return mono;}
static int clock_utc(uint64_t *out){*out=utc;return 0;}
static int random_bytes(void *out,size_t n){unsigned char *p=out;for(size_t i=0;i<n;i++)p[i]=(unsigned char)(entropy+i);entropy++;return 0;}
static int zero_code(void *out,size_t n){assert(n==4);uint32_t x=7;memcpy(out,&x,n);return 0;}
static int load(unsigned slot,void *out,size_t n){assert(n==sizeof(PRRegistry));if(fail_load){fail_load=0;return -1;}if(!present[slot])return 0;memcpy(out,&slots[slot],n);return 1;}
static int store(unsigned slot,const void *data,size_t n){assert(n==sizeof(PRRegistry));stores++;if(fail_store)return -1;memcpy(&slots[slot],data,n);present[slot]=1;return 0;}
static const PRIO io={clock_mono,clock_utc,random_bytes,load,store};
static const char *build="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
static const char *client="11111111111111111111111111111111",*nonce="22222222222222222222222222222222";
static PRState state;
static char out[4096],body[1025],request_id[33],token[33],credential[33];
static unsigned checks;
static void pass(const char *name){checks++;printf("PASS %s\n",name);}
static void fresh(void){memset(slots,0,sizeof(slots));memset(present,0,sizeof(present));fail_store=fail_load=stores=0;mono=1000;utc=1791144000;entropy=1;assert(pr_init(&state,&io,17866,17867,build));}
static int call(const char *method,const char *path,const char *text,int local,int admin,const char *bearer){int r=pr_dispatch(&state,method,path,local,admin,bearer,text,strlen(text),out);assert(strlen(out)<4096&&pr_json_valid(out,strlen(out)));return r;}
static void open_ui(void){snprintf(body,sizeof(body),"{\"protocol\":1,\"control_build_id\":\"%s\"}",build);assert(call("POST","/pairing/native/register",body,1,1,"")==200);assert(call("POST","/pairing/ui/open",body,1,1,"")==200);}
static void request(void){snprintf(body,sizeof(body),"{\"protocol\":1,\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"client_name\":\"Phone \\\"one\\\"\"}",client,nonce);assert(call("POST","/pairing/request",body,0,0,"")==201);assert(pr_json_string(out,strlen(out),"request_id",request_id,33));}
static void confirmation_body(const char *code){snprintf(body,sizeof(body),"{\"protocol\":1,\"request_id\":\"%s\",\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"code\":\"%s\"}",request_id,client,nonce,code);}
static void approve(void){char digest[65];pr_code_digest(request_id,client,nonce,"000007",digest);snprintf(body,sizeof(body),"{\"protocol\":1,\"request_id\":\"%s\",\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"code_sha256\":\"%s\"}",request_id,client,nonce,digest);assert(call("POST","/pairing/ui/approve",body,1,1,"")==200);assert(!strstr(out,"000007")&&!strstr(out,"code_sha256"));}
static void paired(void){fresh();open_ui();request();approve();confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==200);assert(pr_json_string(out,strlen(out),"token",token,33));assert(pr_json_string(out,strlen(out),"credential_id",credential,33));}
int main(void){
    _Static_assert(sizeof(PRRegistry)<4096,"Registry must stay bounded");
    fresh();assert(call("GET","/pairing/info","",0,0,"")==200);assert(!strstr(out,"token")&&!strstr(out,"client_id"));assert(strstr(out,"\"pairing_open\":false"));
    snprintf(body,sizeof(body),"{\"protocol\":1,\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"client_name\":\"Phone\"}",client,nonce);assert(call("POST","/pairing/request",body,0,0,"")==403);pass("public info is nonsecret; closed request refused");
    assert(call("POST","/pairing/ui/open","{\"protocol\":1}",0,1,"")==403);assert(call("POST","/pairing/ui/open","{\"protocol\":1}",1,0,"")==403);pass("LAN administrator and local unauthenticated callers cannot approve");
    open_ui();request();confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==403);pass("code knowledge cannot replace physical approval");
    uint64_t deadline=state.pending.deadline;mono+=1000;request();assert(state.pending.deadline==deadline);assert(strstr(out,"\"expires_in_seconds\":119"));snprintf(body,sizeof(body),"{\"protocol\":1,\"client_id\":\"33333333333333333333333333333333\",\"client_nonce\":\"%s\",\"client_name\":\"Other\"}",nonce);assert(call("POST","/pairing/request",body,0,0,"")==409);pass("nonce retry recovers original request; concurrent replacement refused");
    char code[7];assert(pr_random_code(zero_code,code)&&!strcmp(code,"000007"));approve();assert(state.pending.deadline==deadline);confirmation_body("000007");int before=stores;assert(call("POST","/pairing/confirm",body,0,0,"")==200);assert(stores==before+1);assert(pr_json_string(out,strlen(out),"token",token,33));char first[4096];strcpy(first,out);assert(call("POST","/pairing/confirm",body,0,0,"")==200);assert(!strcmp(first,out)&&stores==before+1);pass("leading-zero code and lost confirmation recover one durable credential");
    for(unsigned i=0;i<2;i++)if(present[i]){const char *raw=(const char *)&slots[i];for(size_t p=0;p+32<=sizeof(PRRegistry);p++)assert(memcmp(raw+p,token,32));}
    pass("only credential digest persists; token never stored");
    assert(call("GET","/pairing/session","",0,0,token)==200);uint64_t expiry;assert(pr_json_uint(out,strlen(out),"expires_at",&expiry)&&expiry==utc+PR_DAYS_SECONDS);assert(!strstr(out,"\"token\""));pass("individual session receipt has exact durable 90-day expiry");
    paired();mono+=1000;utc+=10;before=stores;assert(pr_auth(&state,token,0)==200);assert(stores==before+1&&state.registry.phones[0].last_seen==utc-10);assert(pr_auth(&state,token,1)==200&&state.registry.phones[0].last_seen==utc);PRState reboot;assert(pr_init(&reboot,&io,17866,17867,build));assert(reboot.registry.phones[0].expires==utc+PR_DAYS_SECONDS);pass("validation commits clock high water; renewal and reboot retain expiry");
    paired();utc=state.registry.phones[0].expires-1;assert(pr_auth(&state,token,0)==200);utc++;assert(pr_auth(&state,token,1)==401&&state.registry.phones[0].revoked);utc--;assert(pr_auth(&state,token,0)==503);assert(!pr_init(&reboot,&io,17866,17867,build));utc+=2;assert(pr_init(&reboot,&io,17866,17867,build)&&pr_auth(&reboot,token,0)==401);pass("exact expiry and persisted rollback refusal cannot revive credential");
    paired();snprintf(body,sizeof(body),"{\"protocol\":1,\"credential_id\":\"%s\"}",credential);assert(call("POST","/pairing/ui/revoke",body,1,1,"")==200);assert(pr_auth(&state,token,1)==401);assert(pr_init(&reboot,&io,17866,17867,build)&&pr_auth(&reboot,token,0)==401);pass("native revocation survives reboot");
    paired();utc++;fail_store=1;assert(pr_auth(&state,token,1)==503&&!state.ready);pass("durable write failure disables phone authority before success");
    paired();utc++;fail_load=1;assert(pr_auth(&state,token,1)==503&&!state.ready);fail_load=0;assert(pr_init(&reboot,&io,17866,17867,build));assert(reboot.registry.phones[0].last_seen==utc);pass("committed-but-unconfirmed renewal is not replayed or misreported");
    paired();slots[state.active_slot].device_id[2]^=1;assert(!pr_init(&reboot,&io,17866,17867,build)&&!reboot.ready);pass("corrupt registry does not become an empty permissive registry");
    paired();slots[state.active_slot].version=99;pr_sha(&slots[state.active_slot],offsetof(PRRegistry,checksum),slots[state.active_slot].checksum);assert(!pr_init(&reboot,&io,17866,17867,build));pass("unsupported format rejected even with valid checksum");
    fresh();open_ui();request();approve();for(unsigned i=0;i<5;i++){confirmation_body("123456");assert(call("POST","/pairing/confirm",body,0,0,"")==(i==4?409:422));}assert(state.pending.wrong==5);confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==409);assert(call("POST","/pairing/ui/open","{\"protocol\":1}",1,1,"")==429);pass("five failures exhaust challenge and enforce cooldown");
    fresh();open_ui();request();approve();confirmation_body("000007");char *where=strstr(body,nonce);assert(where);where[0]='3';assert(call("POST","/pairing/confirm",body,0,0,"")==403);assert(state.pending.wrong==0);pass("cross-client or changed nonce cannot consume or recover challenge");
    fresh();open_ui();request();approve();mono+=120000;utc+=120;confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==409);pass("expired challenge wiped and cannot be revived");
    fresh();open_ui();request();approve();mono+=2001;confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==409);pass("abandoned native UI stops unconfirmed approval");
    paired();assert(call("POST","/pairing/ui/list","{\"protocol\":1}",1,1,"")==200);assert(strstr(out,"Phone \\\"one\\\"")&&!strstr(out,token)&&!strstr(out,"digest"));pass("local registry labels escape JSON without credential disclosure");
    assert(!pr_json_valid("{\"a\":1,}",8));char text[65];const char *emoji="{\"name\":\"\\ud83d\\ude00\"}";assert(pr_json_string(emoji,strlen(emoji),"name",text,sizeof(text))&&pr_utf8(text,strlen(text)));const char *bad="{\"name\":\"\\ud800\"}";assert(!pr_json_valid(bad,strlen(bad)));pass("bounded parser validates Unicode and rejects malformed structures");
    fresh();open_ui();assert(call("POST","/pairing/request","{\"protocol\":1,\"protocol\":1}",0,0,"")==400);memset(body,'x',1024);body[1024]=0;assert(call("POST","/pairing/request",body,0,0,"")==400);assert(call("GET","/pairing/session","",0,1,"dddddddddddddddddddddddddddddddd")==401);pass("duplicate authority fields, invalid bound body and legacy session fallback refused");
    fresh();open_ui();request();uint64_t original_deadline=state.pending.deadline;mono+=120000;utc+=120;open_ui();snprintf(body,sizeof(body),"{\"protocol\":1,\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"client_name\":\"Phone\"}",client,nonce);assert(call("POST","/pairing/request",body,0,0,"")==409&&state.pending.deadline==original_deadline);pass("expired nonce cannot restart its deadline when the local window reopens");
    fresh();char clients[9][33],first_token[33]={0};const char *original_client=client;
    for(unsigned i=0;i<8;i++){snprintf(clients[i],33,"%032x",i+10);client=clients[i];open_ui();request();approve();confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==200);if(!i)assert(pr_json_string(out,strlen(out),"token",first_token,33));mono+=120001;utc+=121;}
    snprintf(clients[8],33,"%032x",18);client=clients[8];open_ui();request();approve();confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==409);
    snprintf(body,sizeof(body),"{\"protocol\":1,\"credential_id\":\"%s\"}",state.registry.phones[0].credential_id);assert(call("POST","/pairing/ui/revoke",body,1,1,"")==200);
    confirmation_body("000007");assert(call("POST","/pairing/confirm",body,0,0,"")==200&&state.registry.count==8);assert(pr_auth(&state,first_token,1)==401);client=original_client;
    pass("eight active phones cap; forgetting frees a slot without reviving an old token");
    printf("%u actual pairing state-machine groups passed; physical/native adapters unqualified.\n",checks);return 0;
}
