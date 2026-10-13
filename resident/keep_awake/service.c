#include "service.h"
#include "policy.h"
#include "power_platform.h"
#include "../platform.h"
#define RKA_HEADER_MAX 1536u
/* Wi-Fi power saving and retransmits can exceed a 300 ms request budget.
   Every wait still runs step(), and stopping interrupts the 10 ms polling. */
#define RKA_CLIENT_MS 2000u
static RKAState state;
static char administrator[33];
static int worker_running,lease_active,worker_started;
static int running(void) { return __atomic_load_n(&worker_running,__ATOMIC_ACQUIRE)&&r_running(); }
int rka_active(void) { return __atomic_load_n(&lease_active,__ATOMIC_ACQUIRE); }
static void step(void) {
    uint64_t now=rkap_now();
#ifdef __vita__
    int network=r_network_ready();
#else
    int network=r_network_ready()&&rkap_host_network_ready();
#endif
    if(rka_policy_step(&state,now,network)) rka_policy_tick(&state,now,rkap_tick());
    __atomic_store_n(&lease_active,state.active,__ATOMIC_RELEASE);
}
static int equal(const char *left,const char *right,unsigned size) {
    unsigned difference=0;
    for(unsigned i=0;i<size;i++) difference|=(unsigned char)left[i]^(unsigned char)right[i];
    return difference==0;
}
static int header_name(const char *left,const char *right) {
    while(*left&&*right) {
        unsigned a=(unsigned char)*left++,b=(unsigned char)*right++;
        if(a>='A'&&a<='Z') a+='a'-'A';
        if(b>='A'&&b<='Z') b+='a'-'A';
        if(a!=b) return 0;
    }
    return !*left&&!*right;
}
typedef struct { int post,authorized,content_type;unsigned length; } Request;
static int parse(char *headers,Request *request) {
    R_MEMSET(request,0,sizeof(*request));
    char *end=R_STRSTR(headers,"\r\n");if(!end) return 400;
    *end=0;
    if(!R_STRCMP(headers,"GET /keep-awake/status HTTP/1.1")) request->post=0;
    else if(!R_STRCMP(headers,"POST /keep-awake/lease HTTP/1.1")) request->post=1;
    else return 404;
    int auth_seen=0,length_seen=0,type_seen=0,host_seen=0;
    char *line=end+2;
    while(*line) {
        end=R_STRSTR(line,"\r\n");if(!end) return 400;
        if(end==line) break;
        *end=0;char *colon=R_STRCHR(line,':');if(!colon||colon==line) return 400;
        *colon=0;
        for(char *p=line;*p;p++) if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-')) return 400;
        char *value=colon+1;while(*value==' '||*value=='\t') value++;
        for(char *p=value;*p;p++) if((unsigned char)*p<32&&*p!='\t') return 400;
        if(header_name(line,"Authorization")) {
            if(auth_seen++) return 400;
            request->authorized=R_STRLEN(value)==39&&!R_STRNCMP(value,"Bearer ",7)&&equal(value+7,administrator,32);
        } else if(header_name(line,"Content-Length")) {
            if(length_seen++||!*value) return 400;
            unsigned number=0;
            for(char *p=value;*p;p++) { if(*p<'0'||*p>'9'||number>128) return 400;number=number*10+(unsigned)(*p-'0'); }
            if(number>RKA_WIRE_BYTES) return 400;
            request->length=number;
        } else if(header_name(line,"Content-Type")) {
            if(type_seen++) return 400;
            request->content_type=!R_STRCMP(value,"application/octet-stream");
        } else if(header_name(line,"Transfer-Encoding")||header_name(line,"Expect")) return 400;
        else if(header_name(line,"Host")) { if(host_seen++||!*value) return 400; }
        line=end+2;
    }
    if(!request->authorized) return 401;
    if(!host_seen) return 400;
    if(request->post&&(!length_seen||request->length!=RKA_WIRE_BYTES||!request->content_type)) return 400;
    if(!request->post&&request->length) return 400;
    return 200;
}
static unsigned format(char *reply,size_t size,int code,const char *error) {
    char lease[36]="null",job[36]="null";
    /* Snapshot exactly the clock used by expiry, avoiding active + zero TTL. */
    uint64_t now=state.last_clock_ms,remaining=0,session=0;
    if(state.active) {
        R_SNPRINTF(lease,sizeof(lease),"\"%s\"",state.lease_id);
        R_SNPRINTF(job,sizeof(job),"\"%s\"",state.job_id);
        if(state.expires_ms>now) remaining=state.expires_ms-now;
        if(state.session_expires_ms>now) session=state.session_expires_ms-now;
    }
    int n=R_SNPRINTF(reply,size,
        "{\"app\":\"Vita Resident Keep Awake\",\"protocol\":1,\"resident_build_id\":\"%s\","
        "\"instance_id\":\"%s\",\"clock_ms\":%llu,\"revision\":%u,\"port\":17869,"
        "\"active\":%s,\"lease_id\":%s,\"job_id\":%s,\"remaining_ms\":%llu,"
        "\"session_remaining_ms\":%llu,\"last_tick_ms\":%llu,\"tick_count\":%llu,"
        "\"tick_result\":%d,\"reason\":\"%s\",\"status\":%d,\"error\":%s}",
        R_BUILD_ID,state.instance_id,(unsigned long long)now,state.revision,state.active?"true":"false",lease,job,
        (unsigned long long)remaining,(unsigned long long)session,(unsigned long long)state.last_tick_ms,
        (unsigned long long)state.tick_count,state.tick_result,state.reason,code,error);
    return n>0&&(size_t)n<size?(unsigned)n:0;
}
static int send_all(int socket,const char *data,unsigned size,uint64_t deadline) {
    unsigned done=0;
    while(done<size&&running()) {
        step();uint64_t now=rkap_now();if(now>=deadline||now<deadline-RKA_CLIENT_MS) return 0;
        int n=r_send(socket,data+done,size-done);
        if(n==-2) { r_delay(10);continue; }
        if(n<=0) return 0;
        done+=(unsigned)n;
    }
    return done==size;
}
static void client(int socket) {
    char incoming[RKA_HEADER_MAX+RKA_WIRE_BYTES+1],reply[1400],head[256];
    unsigned used=0,header_bytes=0;Request request={0};
    uint64_t deadline=rkap_now()+RKA_CLIENT_MS;
    int code=400;
    while(running()) {
        step();uint64_t now=rkap_now();if(now>=deadline||now<deadline-RKA_CLIENT_MS) return;
        if(header_bytes&&used-header_bytes==request.length) break;
        if(used>=sizeof(incoming)-1) return;
        int n=r_recv(socket,incoming+used,sizeof(incoming)-1-used);
        if(n==-2) { r_delay(10);continue; }
        if(n<=0) return;
        used+=(unsigned)n;incoming[used]=0;
        if(!header_bytes) {
            char *end=R_STRSTR(incoming,"\r\n\r\n");
            if(!end) { if(used>RKA_HEADER_MAX) return;continue; }
            header_bytes=(unsigned)(end-incoming)+4;
            if(header_bytes>RKA_HEADER_MAX) return;
            /* Preserve body; parse mutates only header characters. */
            code=parse(incoming,&request);
            if(code!=200) break;
        }
        if(used-header_bytes>request.length) { code=400;break; }
    }
    if(!running()) return;
    if(code==200&&request.post) {
        RKARequest command;
        if(!rka_decode(&command,(unsigned char *)incoming+header_bytes,request.length)) code=400;
        else { step();code=rka_policy_apply(&state,&command,rkap_now());step();if(code==200&&!state.active&&command.ttl_ms) code=503; }
    }
    step();
    const char *error=code==200?"null":code==401?"\"administrator_required\"":code==409?"\"stale_or_wrong_owner\"":
        code==503?"\"lease_unavailable\"":code==404?"\"route_not_found\"":"\"invalid_request\"";
    unsigned size;
    if(!request.authorized) {
        int count=R_SNPRINTF(reply,sizeof(reply),"{\"error\":%s}",error);
        size=count>0&&(unsigned)count<sizeof(reply)?(unsigned)count:0;
    } else size=format(reply,sizeof(reply),code,error);
    if(!size) return;
    const char *text=code==200?"OK":code==401?"Unauthorized":code==409?"Conflict":code==503?"Unavailable":code==404?"Not Found":"Bad Request";
    int count=R_SNPRINTF(head,sizeof(head),"HTTP/1.1 %d %s\r\nContent-Type: application/json\r\nContent-Length: %u\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",code,text,size);
    if(count>0&&(unsigned)count<sizeof(head)&&send_all(socket,head,(unsigned)count,deadline)) send_all(socket,reply,size,deadline);
}
static void worker(void) {
    int listener=-1;
    while(running()) {
        step();
        if(listener<0) {
            listener=rkap_listen();
            if(listener<0) { rka_policy_end(&state,"listener_unavailable");__atomic_store_n(&lease_active,0,__ATOMIC_RELEASE);r_delay(100);continue; }
        }
        int socket=r_accept(listener);
        if(socket>=0) { client(socket);r_close_socket(socket); }
        else if(socket==-2) { r_close_socket(listener);listener=-1;rka_policy_end(&state,"listener_lost");__atomic_store_n(&lease_active,0,__ATOMIC_RELEASE); }
        else r_delay(20);
    }
    rka_policy_end(&state,"stopped");__atomic_store_n(&lease_active,0,__ATOMIC_RELEASE);
    if(listener>=0) r_close_socket(listener);
}
int rka_start(const char token[33]) {
    if(worker_started) return -1;
    for(unsigned i=0;i<32;i++) if(!((token[i]>='0'&&token[i]<='9')||(token[i]>='a'&&token[i]<='f'))) return -1;
    if(token[32]) return -1;
    unsigned char random[16];char instance[33];const char *hex="0123456789abcdef";
    if(r_pair_random(random,sizeof(random))<0) return -1;
    for(unsigned i=0;i<16;i++) { instance[i*2]=hex[random[i]>>4];instance[i*2+1]=hex[random[i]&15]; }
    instance[32]=0;rka_policy_init(&state,instance);R_MEMCPY(administrator,token,33);
    __atomic_store_n(&lease_active,0,__ATOMIC_RELEASE);__atomic_store_n(&worker_running,1,__ATOMIC_RELEASE);
    int result=rkap_worker_start(worker);
    if(result<0) { __atomic_store_n(&worker_running,0,__ATOMIC_RELEASE);R_MEMSET(administrator,0,sizeof(administrator));return result; }
    worker_started=1;return 0;
}
int rka_stop(void) {
    if(!worker_started) return 0;
    __atomic_store_n(&worker_running,0,__ATOMIC_RELEASE);
    int result=rkap_worker_join();
    if(result>=0) { worker_started=0;R_MEMSET(administrator,0,sizeof(administrator)); }
    return result;
}
