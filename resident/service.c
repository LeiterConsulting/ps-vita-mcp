/* Authenticated, allocation-free HTTP service. Same code is exercised on the host. */
#include "platform.h"
#include "sha256.h"
#include "pairing.h"

static unsigned char buffer[R_CHUNK];
static char headers[4097];
static char reply[4096];
static PRState pairing_state;
static char phone_token[33];
static void error(int socket,int status,const char *reason);
static uint64_t started,heartbeat,requests,uploads;
static uint64_t idle_deadline,total_deadline;

typedef struct {
    char method[8],path[128],authorization[48],digest[65],mime[64];
    uint32_t length;
    int has_length,has_auth,has_digest,has_mime;
} Request;

static int hex(const char *s,size_t n) {
    if(R_STRLEN(s)!=n) return 0;
    for(size_t i=0;i<n;i++) if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f'))) return 0;
    return 1;
}
static int equal_token(const char *a,const char *b) {
    unsigned difference=0;
    for(unsigned i=0;i<32;i++) difference|=(unsigned char)a[i]^(unsigned char)b[i];
    return difference==0;
}
static int lower_equal(const char *a,const char *b) {
    while(*a&&*b) { char c=*a++; if(c>='A'&&c<='Z') c+=(char)32; if(c!=*b++) return 0; }
    return *a==*b;
}
static int copy(char *out,size_t capacity,const char *s) {
    size_t size=R_STRLEN(s); if(size>=capacity) return 0; R_MEMCPY(out,s,size+1); return 1;
}
static int parse(char *text,Request *request) {
    R_MEMSET(request,0,sizeof(*request));
    char *end=R_STRSTR(text,"\r\n"); if(!end) return 400; *end=0;
    char *space=R_STRCHR(text,' '); if(!space) return 400; *space++=0;
    char *version=R_STRCHR(space,' '); if(!version) return 400; *version++=0;
    if(!copy(request->method,sizeof(request->method),text)||!copy(request->path,sizeof(request->path),space)||R_STRCMP(version,"HTTP/1.1")) return 400;
    char *line=end+2;
    while(*line) {
        end=R_STRSTR(line,"\r\n"); if(!end) return 400; *end=0;
        if(!*line) break;
        if(*line==' '||*line=='\t') return 400;
        char *colon=R_STRCHR(line,':'); if(!colon) return 400; *colon++=0;
        while(*colon==' '||*colon=='\t') colon++;
        if(lower_equal(line,"authorization")) {
            if(request->has_auth++||!copy(request->authorization,sizeof(request->authorization),colon)) return 400;
        } else if(lower_equal(line,"content-length")) {
            if(request->has_length++||!*colon) return 400;
            uint32_t size=0;
            for(const char *p=colon;*p;p++) {
                if(*p<'0'||*p>'9'||size>R_MAX_FILE/10u) return 413;
                size=size*10u+(unsigned)(*p-'0'); if(size>R_MAX_FILE) return 413;
            }
            request->length=size;
        } else if(lower_equal(line,"x-sha256")) {
            if(request->has_digest++||!copy(request->digest,sizeof(request->digest),colon)) return 400;
        } else if(lower_equal(line,"content-type")) {
            if(request->has_mime++||!copy(request->mime,sizeof(request->mime),colon))return 400;
        } else if(lower_equal(line,"transfer-encoding")||lower_equal(line,"expect")) return 400;
        line=end+2;
    }
    return 0;
}
static int timed(void) { uint64_t now=r_now(); return !r_running()||now>=idle_deadline||now>=total_deadline; }
static int send_all(int socket,const void *data,size_t size) {
    const unsigned char *p=data;
    while(size) {
        if(timed()) return 0;
        int n=r_send(socket,p,size);
        if(n>0) { p+=n; size-=(unsigned)n; idle_deadline=r_now()+5000; }
        else if(n==-2) r_delay(5); else return 0;
    }
    return 1;
}
static int response_header(int socket,int status,const char *type,uint32_t length) {
    if(status>=200&&status<300&&phone_token[0]) {
        int renewal=pr_auth(&pairing_state,phone_token,1);
        if(renewal!=200){phone_token[0]=0;error(socket,renewal,"Phone renewal could not be committed");return 0;}
    }
    char text[256]; int n=R_SNPRINTF(text,sizeof(text),"HTTP/1.1 %d Result\r\nContent-Type: %s\r\nContent-Length: %u\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",status,type,(unsigned)length);
    return n>0&&(size_t)n<sizeof(text)&&send_all(socket,text,(unsigned)n);
}
static void respond(int socket,int status,const char *body) {
    idle_deadline=r_now()+5000; total_deadline=r_now()+10000;
    if(response_header(socket,status,"application/json",(uint32_t)R_STRLEN(body))) send_all(socket,body,R_STRLEN(body));
}
static void error(int socket,int status,const char *reason) {
    R_SNPRINTF(reply,sizeof(reply),"{\"error\":\"%s\"}",reason); respond(socket,status,reply);
}
static int filename(const char *path,const char *prefix,char id[33],char leaf[16]) {
    size_t prefix_size=R_STRLEN(prefix);
    if(R_STRNCMP(path,prefix,prefix_size)||R_STRLEN(path)<prefix_size+33) return 0;
    R_MEMCPY(id,path+prefix_size,32); id[32]=0;
    if(!hex(id,32)||path[prefix_size+32]!='/') return 0;
    if(!copy(leaf,16,path+prefix_size+33)) return 0;
    return !R_STRCMP(leaf,"package.vpk")||!R_STRCMP(leaf,"probe.bin");
}
static int storage_path(char *out,size_t size,const char *id,const char *leaf,int part) {
    int n=R_SNPRINTF(out,size,"ux0:data/vita-resident/inbox/%s/%s%s",id,leaf,part?".part":"");
    return n>0&&(size_t)n<size;
}
static int hash_stored(const char *path,uint32_t expected,char digest[65]) {
    int fd=r_open_read(path); if(fd<0) return 0;
    RSha sha; rs_init(&sha); uint32_t count=0; int good=1;
    for(;;) {
        if(timed()) { good=0; break; }
        int n=r_read(fd,buffer,sizeof(buffer));
        if(n<0) { good=0; break; } if(!n) break;
        if((uint32_t)n>expected-count) { good=0; break; }
        count+=(uint32_t)n; rs_update(&sha,buffer,(size_t)n);
    }
    if(r_close_file(fd)<0) good=0;
    rs_final(&sha,digest); return good&&count==expected;
}
static int write_all(int fd,const void *data,size_t size) {
    const unsigned char *p=data;
    while(size) { if(timed()) return 0; int n=r_write(fd,p,size); if(n<=0||(size_t)n>size) return 0; p+=n; size-=(size_t)n; }
    return 1;
}
static void upload(int socket,const Request *request,const unsigned char *initial,size_t initial_size) {
    char id[33],leaf[16],directory[128],part[160],final[160];
    if(!filename(request->path,"/upload/",id,leaf)||!request->has_length||!request->length||!hex(request->digest,64)||initial_size>request->length) { error(socket,400,"Invalid upload metadata"); return; }
    if(!R_STRCMP(leaf,"probe.bin")&&request->length>65536) { error(socket,413,"Probe exceeds 64 KiB"); return; }
    R_SNPRINTF(directory,sizeof(directory),"ux0:data/vita-resident/inbox/%s",id);
    if(r_dir(directory)<0) { error(socket,409,"Attempt exists or storage unavailable; choose a fresh attempt"); return; }
    storage_path(part,sizeof(part),id,leaf,1); storage_path(final,sizeof(final),id,leaf,0);
    int fd=r_open_write(part); if(fd<0) { error(socket,500,"Cannot create part file"); return; }
    RSha sha; rs_init(&sha); uint32_t count=(uint32_t)initial_size; int good=write_all(fd,initial,initial_size); rs_update(&sha,initial,initial_size);
    while(good&&count<request->length) {
        if(timed()) { good=0; break; }
        size_t wanted=request->length-count; if(wanted>sizeof(buffer)) wanted=sizeof(buffer);
        int n=r_recv(socket,buffer,wanted);
        if(n>0) { idle_deadline=r_now()+5000; good=write_all(fd,buffer,(size_t)n); rs_update(&sha,buffer,(size_t)n); count+=(uint32_t)n; }
        else if(n==-2) r_delay(5); else good=0;
    }
    if(r_close_file(fd)<0) good=0;
    if(!good) { error(socket,408,"Incomplete upload; part retained and final file not published"); return; }
    char digest[65],disk_digest[65]; rs_final(&sha,digest);
    if(R_STRCMP(digest,request->digest)) { error(socket,422,"Upload hash mismatch; part retained"); return; }
    if(!hash_stored(part,request->length,disk_digest)||R_STRCMP(disk_digest,digest)) { error(socket,500,"Storage read-back failed; part retained"); return; }
    if(r_rename(part,final)<0) { error(socket,500,"Final rename failed; outcome needs inspection"); return; }
    uploads++;
    R_SNPRINTF(reply,sizeof(reply),"{\"app\":\"Vita Resident\",\"protocol\":1,\"attempt\":\"%s\",\"bytes\":%u,\"sha256\":\"%s\",\"vita_path\":\"%s\",\"storage_readback\":true,\"installation\":\"pending\"}",id,(unsigned)count,digest,final);
    respond(socket,201,reply);
}
static void download(int socket,const Request *request) {
    char id[33],leaf[16],path[160]; uint64_t size=0;
    if(!filename(request->path,"/files/",id,leaf)) { error(socket,404,"Unknown file"); return; }
    storage_path(path,sizeof(path),id,leaf,0);
    if(r_file_size(path,&size)<0||!size||size>R_MAX_FILE) { error(socket,404,"Published file unavailable"); return; }
    int fd=r_open_read(path); if(fd<0) { error(socket,404,"Published file unavailable"); return; }
    if(response_header(socket,200,"application/octet-stream",(uint32_t)size)) {
        uint64_t count=0;
        while(count<size&&!timed()) { size_t wanted=(size-count)>sizeof(buffer)?sizeof(buffer):(size_t)(size-count); int n=r_read(fd,buffer,wanted); if(n<=0||!send_all(socket,buffer,(size_t)n)) break; count+=(unsigned)n; }
    }
    r_close_file(fd);
}
static void status(int socket) {
    RDevice d; r_device(&d);
    R_SNPRINTF(reply,sizeof(reply),"{\"app\":\"Vita Resident\",\"protocol\":1,\"version\":\"0.1.2\",\"build_id\":\"%s\",\"port\":17866,\"started_ms\":%llu,\"uptime_ms\":%llu,\"heartbeat\":%llu,\"requests\":%llu,\"uploads\":%llu,\"battery_percent\":%d,\"charging\":%d,\"clocks_mhz\":[%d,%d,%d,%d],\"network_state\":%d,\"keep_awake\":false,\"max_upload_bytes\":%u,\"process\":\"SceShell user plugin\"}",R_BUILD_ID,(unsigned long long)started,(unsigned long long)(r_now()-started),(unsigned long long)heartbeat,(unsigned long long)requests,(unsigned long long)uploads,d.battery,d.charging,d.cpu,d.bus,d.gpu,d.xbar,d.network,R_MAX_FILE);
    respond(socket,200,reply);
}
static void client(int socket,const char token[33]) {
    phone_token[0]=0;
    size_t used=0,header_size=0; idle_deadline=r_now()+5000; total_deadline=r_now()+120000;
    while(used<sizeof(headers)-1&&!timed()) {
        int n=r_recv(socket,headers+used,sizeof(headers)-1-used);
        if(n>0) {
            idle_deadline=r_now()+5000;
            used+=(unsigned)n; headers[used]=0;
            char *end=R_STRSTR(headers,"\r\n\r\n");
            if(end) { header_size=(size_t)(end-headers)+4; break; }
            for(size_t i=0;i<used;i++) if(headers[i]==0) { error(socket,400,"NUL in header"); return; }
        } else if(n==-2) r_delay(5); else return;
    }
    if(!header_size||header_size>3072) { error(socket,400,"Header exceeds bound or incomplete"); return; }
    /* Only header bytes are textual. Binary body bytes, including NUL, are valid. */
    char saved=headers[header_size]; headers[header_size]=0;
    Request request; int result=parse(headers,&request); headers[header_size]=saved;
    if(result) { error(socket,result,"Invalid request framing"); return; }
    const char *bearer=request.has_auth&&R_STRLEN(request.authorization)==39&&!R_STRNCMP(request.authorization,"Bearer ",7)?request.authorization+7:"";
    int admin=*bearer&&equal_token(bearer,token);
    if(!R_STRNCMP(request.path,"/pairing/",9)) {
        char body[PR_REQUEST_MAX+1];size_t body_used=used-header_size;
        if(request.length>PR_REQUEST_MAX||body_used>request.length){error(socket,413,"Pairing request exceeds bound");return;}
        if(!R_STRCMP(request.method,"GET")) {
            if(request.length||body_used){error(socket,400,"GET body is not supported");return;}
        } else {
            if(!request.has_length){error(socket,400,"Pairing content length required");return;}
            if(!request.has_mime||R_STRNCMP(request.mime,"application/json",16)||(request.mime[16]&&request.mime[16]!=';')){error(socket,415,"Pairing JSON required");return;}
        }
        R_MEMCPY(body,headers+header_size,body_used);
        while(body_used<request.length&&!timed()) {
            int got=r_recv(socket,body+body_used,request.length-body_used);
            if(got>0){body_used+=(unsigned)got;idle_deadline=r_now()+5000;}
            else if(got==-2)r_delay(5);else break;
        }
        if(body_used!=request.length){error(socket,408,"Incomplete pairing request");return;}
        body[body_used]=0;
        int code=pr_dispatch(&pairing_state,request.method,request.path,r_peer_loopback(socket),admin,bearer,body,body_used,reply);
        R_MEMSET(body,0,sizeof(body));respond(socket,code,reply);return;
    }
    if(!admin) {
        int authorization=pr_auth(&pairing_state,bearer,0);
        if(authorization!=200){error(socket,authorization,"Pairing authorization required");return;}
        if(R_STRCMP(request.method,"GET")||R_STRCMP(request.path,"/status")){error(socket,403,"Phone credentials permit inspection only");return;}
        R_MEMCPY(phone_token,bearer,33);
    }
    requests++;
    if(!R_STRCMP(request.method,"GET")) {
        if(request.length||used!=header_size) { error(socket,400,"GET body is not supported"); return; }
        if(!R_STRCMP(request.path,"/status")) status(socket);
        else download(socket,&request);
    } else if(!R_STRCMP(request.method,"POST")) upload(socket,&request,(unsigned char *)headers+header_size,used-header_size);
    else error(socket,405,"Method not supported");
}
void r_service(const char token[33]) {
    started=r_now(); heartbeat=requests=uploads=0;
    if(!hex(token,32)) { r_log("pairing invalid",-1); return; }
    if(r_network_init()<0) { r_log("network initialization failed",-1); return; }
    if(!r_directory_exists("ux0:data/vita-resident/inbox")) { r_log("inbox missing",-1); r_network_end(); return; }
    if(!pr_init(&pairing_state,pr_platform_io(),R_PORT,17867,R_BUILD_ID))r_log("Phone pairing unavailable; legacy auth preserved",-1);
    int listener=-1; uint64_t previous=started;
    r_log("worker ready",0);
    while(r_running()) {
        uint64_t now=r_now(); if(now-previous>=500) { heartbeat++; previous=now; }
        if(!r_network_ready()) { if(listener>=0) r_close_socket(listener); listener=-1; r_delay(100); continue; }
        if(listener<0) { listener=r_listen(); r_log("listener",listener); if(listener<0) { r_delay(1000); continue; } }
        int socket=r_accept(listener);
        if(socket>=0) { client(socket,token); r_close_socket(socket); }
        else if(socket==-2) { r_close_socket(listener); listener=-1; }
        r_delay(25);
    }
    if(listener>=0) r_close_socket(listener);
    r_network_end(); r_log("worker stopped",0);
}
