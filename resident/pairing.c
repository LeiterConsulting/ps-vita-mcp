#include "pairing.h"
#include "platform.h"
#include "sha256.h"
#define PR_MAGIC 0x31525056u
enum { EMPTY, PENDING, APPROVED, COMPLETE, REJECTED, EXHAUSTED, EXPIRED };
static int hex(const char *s,size_t n) {
    if(!s||R_STRLEN(s)!=n)return 0;
    for(size_t i=0;i<n;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return 1;
}
static int same(const char *a,const char *b,size_t n) {
    unsigned x=0;for(size_t i=0;i<n;i++)x|=(unsigned char)a[i]^(unsigned char)b[i];return !x;
}
void pr_sha(const void *data,size_t n,char out[65]) {RSha h;rs_init(&h);rs_update(&h,data,n);rs_final(&h,out);}
void pr_code_digest(const char request[33],const char client[33],const char nonce[33],const char code[7],char out[65]) {
    RSha h;rs_init(&h);rs_update(&h,"VitaPairing1",12);rs_update(&h,request,32);rs_update(&h,client,32);rs_update(&h,nonce,32);rs_update(&h,code,6);rs_final(&h,out);
}
int pr_random_code(int (*random)(void *,size_t),char out[7]) {
    uint32_t value;
    for(unsigned i=0;i<16;i++)if(random(&value,sizeof(value))>=0) {
        if(value>=4294000000u)continue;
        return R_SNPRINTF(out,7,"%06u",(unsigned)(value%1000000u))==6;
    } else return 0;
    return 0;
}
static int random_id(PRState *s,char out[33]) {
    unsigned char bytes[16];if(s->io.random(bytes,sizeof(bytes))<0)return 0;
    static const char digits[]="0123456789abcdef";
    for(unsigned i=0;i<16;i++){out[i*2]=digits[bytes[i]>>4];out[i*2+1]=digits[bytes[i]&15];}out[32]=0;R_MEMSET(bytes,0,sizeof(bytes));return 1;
}
static int clock_now(PRState *s,uint64_t *now) {
    return s->ready&&s->io.utc(now)>=0&&*now>=UINT64_C(1577836800)&&*now<=UINT64_C(4102444800)&&*now>=s->registry.high_water;
}
static int registry_valid(const PRRegistry *r) {
    if(r->magic!=PR_MAGIC||r->version!=1||r->bytes!=sizeof(*r)||r->count>PR_MAX_PHONES||!r->generation||r->device_id[32]||r->checksum[64]||!hex(r->device_id,32)||!hex(r->checksum,64))return 0;
    char digest[65];pr_sha(r,offsetof(PRRegistry,checksum),digest);if(!same(digest,r->checksum,64))return 0;
    for(unsigned i=0;i<r->count;i++) {
        const PRPhone *p=&r->phones[i];
        if(p->client_id[32]||p->credential_id[32]||p->digest[64]||p->label[64]||!hex(p->client_id,32)||!hex(p->credential_id,32)||!hex(p->digest,64)||p->revoked>1||p->last_seen>r->high_water||p->last_seen>UINT64_MAX-PR_DAYS_SECONDS||p->expires!=p->last_seen+PR_DAYS_SECONDS||!pr_utf8(p->label,R_STRLEN(p->label)))return 0;
        for(unsigned j=0;j<i;j++)if(!R_STRCMP(p->client_id,r->phones[j].client_id)||!R_STRCMP(p->credential_id,r->phones[j].credential_id)||same(p->digest,r->phones[j].digest,64))return 0;
    }
    return 1;
}
static int commit(PRState *s,PRRegistry *next) {
    if(!s->ready||s->registry.generation==UINT64_MAX)return 0;
    next->generation=s->registry.generation+1;next->bytes=sizeof(*next);next->magic=PR_MAGIC;next->version=1;
    pr_sha(next,offsetof(PRRegistry,checksum),next->checksum);
    if(!registry_valid(next)) {s->ready=0;return 0;}
    unsigned slot=s->active_slot==0?1:0;PRRegistry check;
    if(s->io.store(slot,next,sizeof(*next))<0||s->io.load(slot,&check,sizeof(check))!=1||!registry_valid(&check)||!same((const char *)&check,(const char *)next,sizeof(check))) {s->ready=0;return 0;}
    s->registry=*next;s->active_slot=(int)slot;return 1;
}
int pr_init(PRState *s,const PRIO *io,unsigned rp,unsigned cp,const char *build) {
    R_MEMSET(s,0,sizeof(*s));s->io=*io;s->resident_port=rp;s->control_port=cp;s->active_slot=-1;
    if(!rp||rp>65535||!cp||cp>65535||!hex(build,64))return 0;
    R_MEMCPY(s->resident_build,build,65);
    PRRegistry a,b;int x=io->load(0,&a,sizeof(a)),y=io->load(1,&b,sizeof(b));
    if(x<0||y<0||(x&&!registry_valid(&a))||(y&&!registry_valid(&b)))return 0;
    if(x&&y&&a.generation==b.generation&&!same((const char *)&a,(const char *)&b,sizeof(a)))return 0;
    if(x||y) {
        s->active_slot=x&&(!y||a.generation>b.generation)?0:1;
        s->registry=s->active_slot==0?a:b;s->ready=1;uint64_t now;
        if(!clock_now(s,&now)){s->ready=0;return 0;}
        if(now>s->registry.high_water){PRRegistry next=s->registry;next.high_water=now;for(unsigned i=0;i<next.count;i++)if(now>=next.phones[i].expires)next.phones[i].revoked=1;return commit(s,&next);}
        return 1;
    }
    s->ready=1;uint64_t now;if(!clock_now(s,&now)||!random_id(s,s->registry.device_id)){s->ready=0;return 0;}
    PRRegistry next=s->registry;next.high_water=now;return commit(s,&next);
}
static int find_token(PRState *s,const char *token) {
    if(!hex(token,32))return -1;
    char digest[65];pr_sha(token,32,digest);int index=-1;
    for(unsigned i=0;i<s->registry.count;i++)if(same(digest,s->registry.phones[i].digest,64))index=(int)i;
    R_MEMSET(digest,0,sizeof(digest));return index;
}
int pr_auth(PRState *s,const char *token,int renew) {
    uint64_t now;if(!clock_now(s,&now))return 503;int i=find_token(s,token);if(i<0)return 401;
    PRPhone *p=&s->registry.phones[i];if(p->revoked)return 401;
    if(now>=p->expires) {PRRegistry next=s->registry;next.phones[i].revoked=1;next.high_water=now;return commit(s,&next)?401:503;}
    if((renew&&now!=p->last_seen)||now>s->registry.high_water) {
        PRRegistry next=s->registry;next.high_water=now;
        if(renew){next.phones[i].last_seen=now;next.phones[i].expires=now+PR_DAYS_SECONDS;}
        if(!commit(s,&next))return 503;
    }
    return 200;
}
static void prune(PRState *s) {
    uint64_t m=s->io.mono(),u=0;
    if(s->pending.phase&&s->pending.phase!=EXPIRED&&(m>=s->pending.deadline||s->io.utc(&u)<0||u>=s->pending.utc_deadline)) {R_MEMSET(s->pending.code_digest,0,65);R_MEMSET(s->pending.recovery_token,0,33);R_MEMSET(s->pending.label,0,65);s->pending.phase=EXPIRED;}
    if(s->ui_open&&(m>=s->ui_deadline||m<s->ui_seen||m-s->ui_seen>2000))s->ui_open=0;
    /* Abandoning UI approval invalidates unconfirmed codes; completed recovery is independent. */
    if(s->pending.phase==APPROVED&&(m<s->ui_seen||m-s->ui_seen>2000)) {R_MEMSET(s->pending.code_digest,0,65);s->pending.phase=EXPIRED;}
}
static int error(char *out,int code,const char *reason) {R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"error\":\"%s\"}",reason);return code;}
static int protocol(const char *body,size_t n) {uint64_t p;return n&&n<=PR_REQUEST_MAX&&pr_json_valid(body,n)&&pr_json_uint(body,n,"protocol",&p)&&p==1;}
static int field(const char *body,size_t n,const char *key,char *out,size_t cap,size_t hexn) {return pr_json_string(body,n,key,out,cap)&&(!hexn||hex(out,hexn));}
static int bound(PRState *s,const char *body,size_t n) {
    char request[33],client[33],nonce[33];return field(body,n,"request_id",request,33,32)&&field(body,n,"client_id",client,33,32)&&field(body,n,"client_nonce",nonce,33,32)&&same(request,s->pending.request_id,32)&&same(client,s->pending.client_id,32)&&same(nonce,s->pending.nonce,32);
}
static void session_json(PRState *s,int index,const char *token,char *out) {
    PRPhone *p=&s->registry.phones[index];
    R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"device_id\":\"%s\",\"client_id\":\"%s\",\"credential_id\":\"%s\",\"inactivity_days\":90,\"last_seen_at\":%llu,\"expires_at\":%llu,\"resident_port\":%u,\"control_port\":%u%s%s%s}",s->registry.device_id,p->client_id,p->credential_id,(unsigned long long)p->last_seen,(unsigned long long)p->expires,s->resident_port,s->control_port,token?",\"token\":\"":"",token?token:"",token?"\"":"");
}
static int request(PRState *s,const char *body,size_t n,char *out) {
    if(!protocol(body,n))return error(out,400,"Malformed pairing request");
    char client[33],nonce[33],label[65]={0};
    if(!field(body,n,"client_id",client,33,32)||!field(body,n,"client_nonce",nonce,33,32)||!field(body,n,"client_name",label,65,0)||!*label)return error(out,400,"Invalid client identity or name");
    for(char *p=label;*p;p++)if((unsigned char)*p<32)*p=' ';
    if(!pr_utf8(label,R_STRLEN(label)))return error(out,400,"Invalid UTF-8 label");
    uint64_t m=s->io.mono(),u;if(!clock_now(s,&u))return error(out,503,"Pairing clock or storage unavailable");
    if(m<s->cooldown)return error(out,429,"Pairing cooldown");
    if(!s->ui_open)return error(out,403,"Open pairing on the Vita");
    if((s->pending.phase==EXPIRED||s->pending.phase==EXHAUSTED||s->pending.phase==REJECTED)&&same(client,s->pending.client_id,32)&&same(nonce,s->pending.nonce,32))return error(out,409,"Challenge ended; use a fresh nonce");
    if(s->pending.phase==PENDING||s->pending.phase==APPROVED||s->pending.phase==COMPLETE) {
        if(!same(client,s->pending.client_id,32)||!same(nonce,s->pending.nonce,32))return error(out,409,"Another request is pending");
    } else {
        if(m<s->rate_start||m-s->rate_start>=60000){s->rate_start=m;s->rate_count=0;}
        if(s->rate_count++>=5)return error(out,429,"Pairing request rate limit");
        /* UTC has whole-second resolution. Monotonic time enforces the exact
           deadline; ceil the RTC bound so rounding cannot end it early. */
        PRPending p={0};p.phase=PENDING;p.deadline=m+120000;p.utc_deadline=u+121;
        if(!random_id(s,p.request_id))return error(out,503,"Random source unavailable");
        R_MEMCPY(p.client_id,client,33);R_MEMCPY(p.nonce,nonce,33);R_MEMCPY(p.label,label,65);s->pending=p;
    }
    R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"device_id\":\"%s\",\"request_id\":\"%s\",\"expires_in_seconds\":%llu,\"approval_required\":true}",s->registry.device_id,s->pending.request_id,(unsigned long long)((s->pending.deadline-m+999)/1000));return 201;
}
static int confirm(PRState *s,const char *body,size_t n,char *out) {
    if(!protocol(body,n))return error(out,400,"Malformed confirmation");
    char code[7];
    if(!field(body,n,"code",code,sizeof(code),0)||R_STRLEN(code)!=6)return error(out,400,"Code must contain six digits");
    for(unsigned i=0;i<6;i++)if(code[i]<'0'||code[i]>'9')return error(out,400,"Code must contain six digits");
    if(!bound(s,body,n))return error(out,403,"Challenge binding rejected");
    if(s->pending.phase==EXPIRED||s->pending.phase==EXHAUSTED)return error(out,409,"Challenge expired or exhausted");
    if(s->io.mono()<s->cooldown)return error(out,429,"Pairing cooldown");
    if(s->pending.phase!=APPROVED&&s->pending.phase!=COMPLETE)return error(out,403,"Vita approval required");
    char digest[65];pr_code_digest(s->pending.request_id,s->pending.client_id,s->pending.nonce,code,digest);R_MEMSET(code,0,sizeof(code));
    if(!same(digest,s->pending.code_digest,64)) {
        if(++s->pending.wrong>=5){s->pending.phase=EXHAUSTED;s->cooldown=s->io.mono()+60000;return error(out,409,"Challenge attempts exhausted");}
        return error(out,422,"Wrong pairing code");
    }
    if(s->pending.phase==COMPLETE) {
        int status=pr_auth(s,s->pending.recovery_token,0),i=find_token(s,s->pending.recovery_token);
        if(status!=200||i<0)return error(out,status,"Credential recovery unavailable");
        session_json(s,i,s->pending.recovery_token,out);return 200;
    }
    uint64_t now;if(!clock_now(s,&now))return error(out,503,"Pairing clock or storage unavailable");
    PRRegistry next=s->registry;unsigned i;
    for(i=0;i<next.count;i++)if(!R_STRCMP(next.phones[i].client_id,s->pending.client_id))break;
    if(i==next.count){
        if(next.count==PR_MAX_PHONES){for(i=0;i<next.count;i++)if(next.phones[i].revoked||now>=next.phones[i].expires)break;if(i==next.count)return error(out,409,"Eight active phones are already paired");}
        else next.count++;
    }
    PRPhone *p=&next.phones[i];R_MEMSET(p,0,sizeof(*p));char token[33];
    if(!random_id(s,token)||!random_id(s,p->credential_id))return error(out,503,"Random source unavailable");
    R_MEMCPY(p->client_id,s->pending.client_id,33);R_MEMCPY(p->label,s->pending.label,65);pr_sha(token,32,p->digest);p->last_seen=now;p->expires=now+PR_DAYS_SECONDS;next.high_water=now;
    if(!commit(s,&next)){R_MEMSET(token,0,sizeof(token));return error(out,503,"Credential storage failed");}
    s->pending.phase=COMPLETE;R_MEMCPY(s->pending.recovery_token,token,33);R_MEMCPY(s->pending.credential_id,p->credential_id,33);session_json(s,(int)i,token,out);R_MEMSET(token,0,sizeof(token));return 200;
}
static int ui(PRState *s,const char *path,const char *body,size_t n,char *out) {
    if(!protocol(body,n))return error(out,400,"Malformed UI request");
    uint64_t m=s->io.mono();
    if(!R_STRCMP(path,"/pairing/ui/open")){
        if(m<s->cooldown)return error(out,429,"Pairing cooldown");
        char build[65];if(!field(body,n,"control_build_id",build,65,64)||!same(build,s->control_build,64))return error(out,403,"Matched protected Control is required before pairing");
        s->ui_open=1;s->ui_deadline=m+120000;s->ui_seen=m;
    }
    else if(!R_STRCMP(path,"/pairing/ui/close")){s->ui_open=0;if(s->pending.phase!=COMPLETE&&s->pending.phase!=EMPTY){s->pending.phase=EXPIRED;R_MEMSET(s->pending.code_digest,0,65);R_MEMSET(s->pending.recovery_token,0,33);R_MEMSET(s->pending.label,0,65);}}
    else if(!R_STRCMP(path,"/pairing/ui/poll"))s->ui_seen=m;
    else if(!R_STRCMP(path,"/pairing/ui/approve")) {
        char digest[65];if(!s->ui_open||!bound(s,body,n)||!field(body,n,"code_sha256",digest,65,64))return error(out,403,"Physical approval binding required");
        if(s->pending.phase==APPROVED&&!same(digest,s->pending.code_digest,64))return error(out,409,"Approval already recorded");
        if(s->pending.phase!=PENDING&&s->pending.phase!=APPROVED)return error(out,409,"Request is unavailable");
        R_MEMCPY(s->pending.code_digest,digest,65);s->pending.phase=APPROVED;s->ui_seen=m;
    } else if(!R_STRCMP(path,"/pairing/ui/reject")) {if(!bound(s,body,n))return error(out,403,"Rejection binding required");s->pending.phase=REJECTED;R_MEMSET(s->pending.code_digest,0,65);}
    else if(!R_STRCMP(path,"/pairing/ui/revoke")) {
        char id[33];if(!field(body,n,"credential_id",id,33,32))return error(out,400,"Invalid credential identity");
        unsigned i;for(i=0;i<s->registry.count;i++)if(!R_STRCMP(id,s->registry.phones[i].credential_id))break;
        if(i==s->registry.count)return error(out,404,"Unknown credential");
        uint64_t now;if(!clock_now(s,&now))return error(out,503,"Clock unavailable");
        PRRegistry next=s->registry;next.phones[i].revoked=1;next.high_water=now;if(!commit(s,&next))return error(out,503,"Revocation storage failed");
        return error(out,200,"Credential revoked; phone has no write or input authority");
    } else if(!R_STRCMP(path,"/pairing/ui/list")) {
        int used=R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"phones\":[");
        for(unsigned i=0;i<s->registry.count;i++) {PRPhone *p=&s->registry.phones[i];char label[400];if(!pr_quote(label,sizeof(label),p->label))return error(out,500,"Label encoding failed");
            int count=R_SNPRINTF(out+used,PR_JSON_MAX-(unsigned)used,"%s{\"credential_id\":\"%s\",\"client_name\":%s,\"last_seen_at\":%llu,\"expires_at\":%llu,\"revoked\":%s}",i?",":"",p->credential_id,label,(unsigned long long)p->last_seen,(unsigned long long)p->expires,p->revoked?"true":"false");
            if(count<0||(unsigned)count>=PR_JSON_MAX-(unsigned)used-3)return error(out,500,"Registry response exceeds bound");
            used+=count;
        }R_MEMCPY(out+used,"]}",3);return 200;
    } else return error(out,404,"Unknown local UI operation");
    char label[400];if(!pr_quote(label,sizeof(label),s->pending.label))return error(out,500,"Label encoding failed");
    static const char *states[]={"none","pending","approved","complete","rejected","exhausted","expired"};
    uint64_t remaining=s->pending.deadline>m?s->pending.deadline-m:0;
    R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"pairing_open\":%s,\"approval_state\":\"%s\",\"client_name\":%s,\"request_id\":\"%s\",\"client_id\":\"%s\",\"client_nonce\":\"%s\",\"remaining_ms\":%llu}",s->ui_open?"true":"false",states[s->pending.phase],label,s->pending.request_id,s->pending.client_id,s->pending.nonce,(unsigned long long)remaining);return 200;
}
int pr_dispatch(PRState *s,const char *method,const char *path,int local,int admin,const char *bearer,const char *body,size_t n,char out[PR_JSON_MAX]) {
    prune(s);if(!s->ready)return error(out,503,"Pairing registry unavailable; Windows authentication is independent");
    if(!R_STRCMP(path,"/pairing/info")&&!R_STRCMP(method,"GET")&&!n) {
        R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"device_id\":\"%s\",\"pairing_open\":%s,\"code_lifetime_seconds\":120,\"inactivity_days\":90,\"resident_port\":%u,\"control_port\":%u,\"resident_version\":\"0.1.2\",\"resident_build_id\":\"%s\",\"control_version\":\"%s\",\"control_build_id\":\"%s\"}",s->registry.device_id,s->ui_open?"true":"false",s->resident_port,s->control_port,s->resident_build,*s->control_build?"0.3.4":"unavailable",s->control_build);return 200;
    }
    if(!R_STRCMP(path,"/pairing/session")&&!R_STRCMP(method,"GET")&&!n) {int code=pr_auth(s,bearer,1);if(code!=200)return error(out,code,"Individual credential rejected or renewal unavailable");session_json(s,find_token(s,bearer),0,out);return 200;}
    if(R_STRCMP(method,"POST")||n>PR_REQUEST_MAX)return error(out,n>PR_REQUEST_MAX?413:405,"Pairing framing rejected");
    if(!R_STRCMP(path,"/pairing/request"))return request(s,body,n,out);
    if(!R_STRCMP(path,"/pairing/confirm"))return confirm(s,body,n,out);
    if(!local||!admin)return error(out,403,"Local Vita UI or native authority required");
    if(!R_STRNCMP(path,"/pairing/ui/",12))return ui(s,path,body,n,out);
    if(!protocol(body,n))return error(out,400,"Malformed native request");
    if(!R_STRCMP(path,"/pairing/native/privacy")) {
        int allowed=s->pending.phase!=APPROVED&&s->pending.phase!=COMPLETE;
        R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"capture_allowed\":%s}",allowed?"true":"false");return 200;
    }
    if(!R_STRCMP(path,"/pairing/native/register")) {char id[65];if(!field(body,n,"control_build_id",id,65,64))return error(out,400,"Invalid build identity");R_MEMCPY(s->control_build,id,65);return error(out,200,"Native Control identity registered");}
    if(!R_STRCMP(path,"/pairing/native/validate")||!R_STRCMP(path,"/pairing/native/renew")) {
        char token[33];if(!field(body,n,"token",token,33,32))return error(out,400,"Invalid individual credential");int code=pr_auth(s,token,!R_STRCMP(path,"/pairing/native/renew"));R_MEMSET(token,0,sizeof(token));
        if(code!=200)return error(out,code,"Individual credential rejected or renewal unavailable");
        R_SNPRINTF(out,PR_JSON_MAX,"{\"app\":\"Vita Companion Pairing\",\"protocol\":1,\"authorized\":true}");return 200;
    }
    return error(out,404,"Unknown pairing operation");
}
