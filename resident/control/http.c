#include "control_platform.h"
#include "lease.h"
#include "rle.h"
/* Authenticated, allocation-free HTTP service. Same code is exercised on the host. */
#include "platform.h"
#include "sha256.h"

static unsigned char buffer[R_CHUNK];
static char headers[4097];
static char reply[8192];
static uint64_t started,heartbeat,requests,uploads;
static uint64_t idle_deadline,total_deadline;

typedef struct {
    char method[8],path[256],authorization[48],digest[65];
    uint32_t length;
    int has_length,has_auth,has_digest;
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
        int n=r_send(socket,p,size>R_CHUNK?R_CHUNK:size);
        if(n>0) { p+=n; size-=(unsigned)n; idle_deadline=r_now()+5000; }
        else if(n==-2) r_delay(5); else return 0;
    }
    return 1;
}
static int response_header(int socket,int status,const char *type,uint32_t length) {
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
static int filename(const char *path,const char *prefix,char id[33],char leaf[64]) {
    size_t prefix_size=R_STRLEN(prefix);
    if(R_STRNCMP(path,prefix,prefix_size)||R_STRLEN(path)<prefix_size+33) return 0;
    R_MEMCPY(id,path+prefix_size,32); id[32]=0;
    if(!hex(id,32)||path[prefix_size+32]!='/') return 0;
    if(!copy(leaf,64,path+prefix_size+33)) return 0;
    if(!*leaf||!R_STRCMP(leaf,".")||!R_STRCMP(leaf,"..")) return 0;
    for(const char *p=leaf;*p;p++) if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='.'||*p=='_'||*p=='-')) return 0;
    return R_STRLEN(leaf)<=63;
}
static int storage_path(char *out,size_t size,const char *id,const char *leaf,int part) {
    int n=R_SNPRINTF(out,size,"ux0:data/vita-control/workspace/%s/%s%s",id,leaf,part?".part":"");
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
    char id[33],leaf[64],directory[192],part[256],final[256];
    if(!filename(request->path,"/workspace/write/",id,leaf)||!request->has_length||!request->length||!hex(request->digest,64)||initial_size>request->length) { error(socket,400,"Invalid upload metadata"); return; }
    if(!R_STRCMP(leaf,"probe.bin")&&request->length>65536) { error(socket,413,"Probe exceeds 64 KiB"); return; }
    R_SNPRINTF(directory,sizeof(directory),"ux0:data/vita-control/workspace/%s",id);
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
    R_SNPRINTF(reply,sizeof(reply),"{\"app\":\"Vita Control\",\"protocol\":1,\"attempt\":\"%s\",\"bytes\":%u,\"sha256\":\"%s\",\"vita_path\":\"%s\",\"storage_readback\":true,\"installation\":\"not performed\"}",id,(unsigned)count,digest,final);
    respond(socket,201,reply);
}
static void download(int socket,const Request *request) {
    char id[33],leaf[64],path[256]; uint64_t size=0;
    if(!filename(request->path,"/workspace/read/",id,leaf)) { error(socket,404,"Unknown file"); return; }
    storage_path(path,sizeof(path),id,leaf,0);
    if(r_file_size(path,&size)<0||!size||size>R_MAX_FILE) { error(socket,404,"Published file unavailable"); return; }
    int fd=r_open_read(path); if(fd<0) { error(socket,404,"Published file unavailable"); return; }
    if(response_header(socket,200,"application/octet-stream",(uint32_t)size)) {
        uint64_t count=0;
        while(count<size&&!timed()) { size_t wanted=(size-count)>sizeof(buffer)?sizeof(buffer):(size_t)(size-count); int n=r_read(fd,buffer,wanted); if(n<=0||!send_all(socket,buffer,(size_t)n)) break; count+=(unsigned)n; }
    }
    r_close_file(fd);
}

static unsigned char pixels[RC_MAX_FRAME];
static unsigned char encoded[RC_MAX_FRAME+(RC_MAX_FRAME/3+127)/128];
static int read_body(int socket,const Request *request,void *out,size_t expected,const void *initial,size_t used) {
    if(!request->has_length||request->length!=expected||used>expected) return 0;
    R_MEMCPY(out,initial,used);
    while(used<expected&&!timed()) {
        int n=r_recv(socket,(unsigned char *)out+used,expected-used);
        if(n>0) { used+=(unsigned)n; idle_deadline=r_now()+5000; }
        else if(n==-2) r_delay(5); else return 0;
    }
    return used==expected;
}
static void control_status(int socket) {
    RReadback state={0}; RDevice device; r_device(&device);
    RPState work={0};rp_read(&work);uint64_t now=r_now(),work_remaining=work.expires_ms>now?work.expires_ms-now:0;
    int result=rc_readback(&state);
    if(result<0||state.magic!=RC_READ_MAGIC||state.abi!=RC_ABI) { error(socket,503,"Control helper unavailable"); return; }
    uint64_t remaining=state.lease.active&&state.lease.expires_ms>state.sample_ms?state.lease.expires_ms-state.sample_ms:0;
    R_SNPRINTF(reply,sizeof(reply),"{\"app\":\"Vita Control\",\"version\":\"" RC_VERSION "\",\"abi\":2,\"build_id\":\"%s\",\"port\":17867,\"uptime_ms\":%llu,\"battery_percent\":%d,\"sample_ms\":%llu,\"lease_remaining_ms\":%llu,\"lease_target_pid\":%d,\"lease_buttons\":%u,\"lease_flags\":%u,\"release_count\":%u,\"last_release_reason\":%u,\"last_release_ms\":%llu,\"capture_codecs\":[\"rgb\",\"rle\"],\"input_sample_result\":%d,\"effective_buttons\":%u,\"effective_sticks\":[%u,%u,%u,%u],\"input_source\":\"effective driver sample; may include emulation\",\"power_protocol\":1,\"work_remaining_ms\":%llu,\"keep_awake\":%s}",R_BUILD_ID,(unsigned long long)(r_now()-started),device.battery,(unsigned long long)state.sample_ms,(unsigned long long)remaining,state.lease.input.target_pid,state.lease.input.buttons,state.lease.input.flags,state.lease.releases,state.lease.release_reason,(unsigned long long)state.lease.released_ms,state.sample_result,state.buttons,state.lx,state.ly,state.rx,state.ry,(unsigned long long)work_remaining,work_remaining?"true":"false");
    respond(socket,200,reply);
}
static void capture(int socket,unsigned scale,int compress) {
    RFrame frame={0}; int result=rc_capture(pixels,&frame,scale);
    if(result<0) { error(socket,503,"Framebuffer unavailable or changed process"); return; }
    if(frame.magic!=RC_FRAME_MAGIC||frame.abi!=RC_ABI||frame.width>480||frame.height>272||!frame.width||!frame.height||frame.bytes!=frame.width*frame.height*3||frame.bytes>sizeof(pixels)) { error(socket,500,"Invalid frame metadata"); return; }
    _Static_assert(sizeof(RFrame)==64,"Frame wire header must be 64 bytes");
    if(compress) {
        uint64_t begin=r_now(); size_t n=rc_rle_encode(pixels,frame.bytes,encoded,sizeof(encoded));
        if(!n) { error(socket,500,"Frame encoding failed"); return; }
        RRleHeader codec={RC_RLE_MAGIC,(uint32_t)n,(uint32_t)((r_now()-begin)*1000)};
        if(response_header(socket,200,"application/x-vita-rgb-rle",sizeof(frame)+sizeof(codec)+n)&&send_all(socket,&frame,sizeof(frame))&&send_all(socket,&codec,sizeof(codec))) send_all(socket,encoded,n);
    } else if(response_header(socket,200,"application/x-vita-rgb",sizeof(frame)+frame.bytes)&&send_all(socket,&frame,sizeof(frame))) send_all(socket,pixels,frame.bytes);
}
static void work_status(int socket) {
    RPState state={0};if(rp_read(&state)<0) { error(socket,503,"Work power service unavailable");return; }
    uint64_t now=r_now(),remaining=state.expires_ms>now?state.expires_ms-now:0;
    char diagnostics[2][512];
    for(unsigned panel=0;panel<2;panel++) {
        const RTouchPanel *d=&state.touch_diagnostics[panel];
        R_SNPRINTF(diagnostics[panel],sizeof(diagnostics[panel]),"{\"reader_pid\":%d,\"last_reader_pid\":%d,\"native_contacts\":%u,\"reads\":%u,\"advances\":%u,\"hook_reads\":%u,\"source_ticks\":%llu,\"received_ms\":%llu,\"changed_ms\":%llu}",d->reader_pid,d->last_reader_pid,d->native_contacts,d->reads,d->advances,d->hook_reads,(unsigned long long)d->source_ticks,(unsigned long long)d->received_ms,(unsigned long long)d->changed_ms);
    }
    R_SNPRINTF(reply,sizeof(reply),"{\"app\":\"Vita Work Power\",\"abi\":2,\"lease_remaining_ms\":%llu,\"idle_ms\":%u,\"idle_elapsed_ms\":%llu,\"dim_percent\":%u,\"dimmed\":%s,\"brightness\":%d,\"restore_brightness\":%d,\"brightness_result\":%d,\"power_tick_result\":%d,\"motion_result\":%d,\"motion_fresh\":%s,\"last_activity_flags\":%u,\"touch_read_result\":%d,\"physical_touch_panels\":%u,\"touch_source_pid\":%d,\"touch_sample_ms\":%llu,\"touch_diagnostics\":[%s,%s],\"input_activity\":\"buttons, additive stick estimate, physical touch sampled by foreground app and motion; synthetic input is filtered\"}",(unsigned long long)remaining,state.idle_ms,(unsigned long long)(now-state.last_activity_ms),state.dim_percent,state.dimmed?"true":"false",state.current,state.original,state.brightness_result,state.tick_result,state.motion_result,state.motion_valid?"true":"false",state.activity_flags,state.touch_result,state.touch_panels,state.touch_pid,(unsigned long long)state.touch_sample_ms,diagnostics[0],diagnostics[1]);
    respond(socket,200,reply);
}
static int list_path(const char *request,char path[192],unsigned *offset) {
    const char *s=request+16; /* /workspace/list/ */
    unsigned value=0,n=0;
    while(*s>='0'&&*s<='9') { if(++n>4) return 0; value=value*10+(unsigned)(*s++-'0'); }
    if(!n||*s++!='/'||value>1000) return 0;
    if(*s&&!hex(s,32)) return 0;
    *offset=value; R_SNPRINTF(path,192,"ux0:data/vita-control/workspace%s%s",*s?"/":"",s); return 1;
}
static void listing(int socket,const Request *request) {
    char path[192]; unsigned offset=0; RCEntry entries[32]; int more=0;
    if(!list_path(request->path,path,&offset)) { error(socket,400,"Invalid workspace path"); return; }
    int count=rc_list(path,offset,entries,&more);
    if(count<0) { error(socket,404,"Workspace directory unavailable"); return; }
    int used=R_SNPRINTF(reply,sizeof(reply),"{\"path\":\"%s\",\"offset\":%u,\"more\":%s,\"entries\":[",path,offset,more?"true":"false");
    for(int i=0;i<count;i++) {
        for(const char *p=entries[i].name;*p;p++) if(!((*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='.'||*p=='_'||*p=='-')) { error(socket,409,"Unsupported workspace entry name"); return; }
        int n=R_SNPRINTF(reply+used,sizeof(reply)-(unsigned)used,"%s{\"name\":\"%s\",\"bytes\":%llu,\"directory\":%s}",i?",":"",entries[i].name,(unsigned long long)entries[i].bytes,entries[i].directory?"true":"false");
        if(n<=0||(unsigned)n>=sizeof(reply)-(unsigned)used-4) { error(socket,500,"Workspace listing exceeds bound"); return; }
        used+=n;
    }
    R_MEMCPY(reply+used,"]}",3); respond(socket,200,reply);
}
static void file_info(int socket,const Request *request,int remove) {
    char id[33],leaf[64],path[256],digest[65]; uint64_t size=0;
    const char *prefix=remove?"/workspace/delete/":"/workspace/stat/";
    if(!filename(request->path,prefix,id,leaf)) { error(socket,400,"Invalid workspace path"); return; }
    storage_path(path,sizeof(path),id,leaf,0);
    if(r_file_size(path,&size)<0||size>R_MAX_FILE||!hash_stored(path,(uint32_t)size,digest)) { error(socket,404,"Workspace file unavailable"); return; }
    if(remove) {
        if(!hex(request->digest,64)||R_STRCMP(digest,request->digest)) { error(socket,409,"Expected file hash differs"); return; }
        if(rc_remove(path)<0) { error(socket,500,"File removal failed; inspect outcome"); return; }
    }
    R_SNPRINTF(reply,sizeof(reply),"{\"vita_path\":\"%s\",\"bytes\":%llu,\"sha256\":\"%s\",\"removed\":%s}",path,(unsigned long long)size,digest,remove?"true":"false"); respond(socket,200,reply);
}
static int permitted_app(const char *title) { return !R_STRCMP(title,"CHRS00003")||!R_STRCMP(title,"CHRS00009")||!R_STRCMP(title,"CHRS00012"); }
static void command(int socket,const Request *request,const void *initial,size_t used) {
    if(!R_STRCMP(request->path,"/power/lease")) {
        RPConfig config={0};
        if(!read_body(socket,request,&config,sizeof(config),initial,used)||!rp_valid(&config)) { error(socket,400,"Invalid work lease");return; }
        if(rp_set(&config)<0) { error(socket,503,"Work power service unavailable");return; }
        work_status(socket);return;
    }
    if(!R_STRCMP(request->path,"/input")) {
        RInput input={0};
        if(!read_body(socket,request,&input,sizeof(input),initial,used)||!rlease_valid(&input)) { error(socket,400,"Invalid bounded input state"); return; }
        int result=rc_input(&input);
        if(result<0) { error(socket,409,"Input target changed or helper unavailable"); return; }
        control_status(socket); return;
    }
    if(request->length||used) { error(socket,400,"Command body must be empty"); return; }
    if(!R_STRCMP(request->path,"/release")) {
        if(rc_release()<0) { error(socket,503,"Control helper unavailable"); return; }
        control_status(socket); return;
    }
    if(!R_STRNCMP(request->path,"/workspace/delete/",18)) { file_info(socket,request,1); return; }
    int launch=!R_STRNCMP(request->path,"/app/launch/",12), quit=!R_STRNCMP(request->path,"/app/quit/",10);
    if(launch||quit) {
        const char *title=request->path+(launch?12:10);
        if(!permitted_app(title)) { error(socket,403,"App is outside development allowlist"); return; }
        rc_release(); int result=rc_app(launch,title);
        R_SNPRINTF(reply,sizeof(reply),"{\"title_id\":\"%s\",\"action\":\"%s\",\"native_result\":%d,\"runtime_observation\":\"pending\"}",title,launch?"launch":"quit",result);
        respond(socket,result<0?409:200,reply); return;
    }
    error(socket,404,"Unknown control operation");
}
static void client(int socket,const char token[33]) {
    size_t used=0,header_size=0; idle_deadline=r_now()+5000; total_deadline=r_now()+120000;
    while(used<sizeof(headers)-1&&!timed()) {
        int n=r_recv(socket,headers+used,sizeof(headers)-1-used);
        if(n>0) {
            idle_deadline=r_now()+5000; used+=(unsigned)n; headers[used]=0;
            char *end=R_STRSTR(headers,"\r\n\r\n");
            if(end) { header_size=(size_t)(end-headers)+4; break; }
            for(size_t i=0;i<used;i++) if(headers[i]==0) { error(socket,400,"NUL in header"); return; }
        } else if(n==-2) r_delay(5); else return;
    }
    if(!header_size||header_size>3072) { error(socket,400,"Header exceeds bound or incomplete"); return; }
    char saved=headers[header_size]; headers[header_size]=0;
    Request request; int result=parse(headers,&request); headers[header_size]=saved;
    if(result) { error(socket,result,"Invalid request framing"); return; }
    if(!request.has_auth||R_STRLEN(request.authorization)!=39||R_STRNCMP(request.authorization,"Bearer ",7)||!equal_token(request.authorization+7,token)) { error(socket,401,"Pairing authorization required"); return; }
    requests++;
    if(!R_STRCMP(request.method,"GET")) {
        if(request.length||used!=header_size) { error(socket,400,"GET body is not supported"); return; }
        if(!R_STRCMP(request.path,"/status")) control_status(socket);
        else if(!R_STRCMP(request.path,"/power/status")) work_status(socket);
        else if(!R_STRCMP(request.path,"/screen/preview")) capture(socket,4,0);
        else if(!R_STRCMP(request.path,"/screen/detail")) capture(socket,2,0);
        else if(!R_STRCMP(request.path,"/screen/preview/rle")) capture(socket,4,1);
        else if(!R_STRCMP(request.path,"/screen/detail/rle")) capture(socket,2,1);
        else if(!R_STRNCMP(request.path,"/workspace/list/",16)) listing(socket,&request);
        else if(!R_STRNCMP(request.path,"/workspace/stat/",16)) file_info(socket,&request,0);
        else download(socket,&request);
    } else if(!R_STRCMP(request.method,"POST")) {
        if(!R_STRNCMP(request.path,"/workspace/write/",17)) upload(socket,&request,(unsigned char *)headers+header_size,used-header_size);
        else command(socket,&request,(unsigned char *)headers+header_size,used-header_size);
    } else error(socket,405,"Method not supported");
}
void r_service(const char token[33]) {
    started=r_now(); heartbeat=requests=uploads=0;
    if(!hex(token,32)||r_network_init()<0||!r_directory_exists("ux0:data/vita-control/workspace")) { r_log("control startup failed",-1); return; }
    int listener=-1;
    while(r_running()) {
        if(!r_network_ready()) { rc_release(); if(listener>=0) r_close_socket(listener); listener=-1; r_delay(100); continue; }
        if(listener<0) { listener=r_listen(); r_log("control listener",listener); if(listener<0) { r_delay(1000); continue; } }
        int socket=r_accept(listener);
        if(socket>=0) { client(socket,token); r_close_socket(socket); }
        else if(socket==-2) { r_close_socket(listener); listener=-1; }
        r_delay(10);
    }
    rc_release(); if(listener>=0) r_close_socket(listener); r_network_end();
}
