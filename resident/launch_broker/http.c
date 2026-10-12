/* Strict JSON/route boundary. The trusted service owns HTTP framing, token
 * authentication, serialization and the post-response/socket-close hook. */
#include "http.h"
#include "../platform.h"

typedef struct { const unsigned char *p,*end; } Json;

static void space(Json *j) {
    while(j->p<j->end && (*j->p==' '||*j->p=='\t'||*j->p=='\r'||*j->p=='\n')) j->p++;
}

static int take(Json *j,unsigned char c) {
    space(j);
    if(j->p==j->end || *j->p!=c) return 0;
    j->p++;
    return 1;
}

static int string(Json *j,char *out,size_t capacity) {
    if(!capacity||!take(j,'"')) return 0;
    size_t used=0;
    while(j->p<j->end) {
        unsigned char c=*j->p++;
        if(c=='"') { out[used]=0;return 1; }
        /* The seven fixed keys and hex/title values need no escape encoding.
         * Reject alternate spellings rather than normalize ambiguous JSON. */
        if(c<32||c>126||c=='\\'||used+1>=capacity) return 0;
        out[used++]=(char)c;
    }
    return 0;
}

static int number(Json *j,uint64_t *out) {
    space(j);
    if(j->p==j->end||*j->p<'0'||*j->p>'9') return 0;
    if(*j->p=='0') {
        j->p++;
        if(j->p<j->end && *j->p>='0' && *j->p<='9') return 0;
        *out=0;
        return 1;
    }
    uint64_t value=0;
    while(j->p<j->end && *j->p>='0' && *j->p<='9') {
        unsigned digit=(unsigned)(*j->p++-'0');
        if(value>(UINT64_MAX-digit)/10u) return 0;
        value=value*10u+digit;
    }
    *out=value;
    return 1;
}

static int hex(const char *value,size_t size) {
    for(size_t i=0;i<size;i++) {
        if(!((value[i]>='0'&&value[i]<='9')||(value[i]>='a'&&value[i]<='f'))) return 0;
    }
    return value[size]==0;
}

static int request(const void *body,size_t size,LBRequest *out) {
    if(!body||!size||size>LB_HTTP_BODY_MAX) return 0;
    const unsigned char *raw=body;
    for(size_t i=0;i<size;i++) if(!raw[i]) return 0;
    Json j={raw,raw+size};
    R_MEMSET(out,0,sizeof(*out));
    out->auth.role=LB_ROLE_ADMIN;
    if(!take(&j,'{')) return 0;
    unsigned seen=0;
    for(unsigned count=0;count<7;count++) {
        char key[32];
        if(count&&!take(&j,',')) return 0;
        if(!string(&j,key,sizeof(key))||!take(&j,':')) return 0;
        static const char *const fields[]={"attempt","title_id","expected_devloop_build","resident_build_id","instance_id","issued_ms","ttl_ms"};
        unsigned index;
        for(index=0;index<7;index++) if(!R_STRCMP(key,fields[index])) break;
        if(index==7||(seen&(1u<<index))) return 0;
        seen|=1u<<index;
        switch(index) {
        case 0: if(!string(&j,out->attempt,sizeof(out->attempt))) return 0;break;
        case 1: if(!string(&j,out->title,sizeof(out->title))) return 0;break;
        case 2: if(!string(&j,out->devloop_build,sizeof(out->devloop_build))) return 0;break;
        case 3: if(!string(&j,out->auth.resident_build,sizeof(out->auth.resident_build))) return 0;break;
        case 4: if(!string(&j,out->auth.instance,sizeof(out->auth.instance))) return 0;break;
        case 5: if(!number(&j,&out->issued_ms)) return 0;break;
        case 6: {
            uint64_t value;
            if(!number(&j,&value)||value>UINT32_MAX) return 0;
            out->ttl_ms=(uint32_t)value;
            break;
        }
        }
    }
    if(seen!=127u||!take(&j,'}')) return 0;
    space(&j);
    return j.p==j.end;
}

static int error(char *reply,size_t capacity,int code) {
    if(reply&&capacity) {
        int count=R_SNPRINTF(reply,capacity,"{\"error\":\"Launch broker request rejected\",\"code\":%d}",code);
        if(count<0||(size_t)count>=capacity) reply[0]=0;
        reply[capacity-1]=0;
    }
    return code;
}

static const char *reason(LBReason value) {
    static const char *const names[]={"none","restart","storage","response_incomplete","disabled","expiry","clock","native","observation"};
    return (unsigned)value<=LB_REASON_OBSERVATION ? names[value] : "invalid";
}

static int receipt_json(const LBReceipt *value,char *reply,size_t capacity) {
    if(!lb_receipt_valid(value)) return 0;
    char observation[512];
    if(value->samples) {
        const LBObservation *o=&value->observation;
        int count=R_SNPRINTF(observation,sizeof(observation),
            "{\"title_id\":\"%s\",\"version\":\"%s\",\"build_id\":\"%s\",\"pid\":%d,\"run\":\"%s\",\"frame\":%llu,\"revision\":%llu,\"paused\":%s,\"faulted\":%s}",
            o->title,o->version,o->build,(int)o->pid,o->run,(unsigned long long)o->frame,
            (unsigned long long)o->revision,o->paused?"true":"false",o->faulted?"true":"false");
        if(count<0||(size_t)count>=sizeof(observation)) return 0;
    } else R_MEMCPY(observation,"null",5);
    int count=R_SNPRINTF(reply,capacity,
        "{\"app\":\"Vita Resident Launch Broker\",\"protocol\":1,\"attempt\":\"%s\",\"title_id\":\"%s\",\"expected_devloop_build\":\"%s\",\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"state\":\"%s\",\"reason\":\"%s\",\"issued_ms\":%llu,\"expires_ms\":%llu,\"accepted_ms\":%llu,\"dispatch_ms\":%llu,\"dispatch_count\":%u,\"native_confirmed\":%s,\"native_result\":%d,\"samples\":%u,\"observation\":%s}",
        value->attempt,value->title,value->devloop_build,value->resident_build,value->instance,
        lb_state_name(value->state),reason(value->reason),(unsigned long long)value->issued_ms,
        (unsigned long long)value->expires_ms,(unsigned long long)value->accepted_ms,
        (unsigned long long)value->dispatch_ms,value->dispatch_count,value->native_confirmed?"true":"false",
        (int)value->native_result,value->samples,observation);
    return count>=0&&(size_t)count<capacity;
}

int lb_http_dispatch(LBCore *core,int admin,const char *method,const char *path,
                     const void *body,size_t size,char *reply,size_t capacity,LBDeferred *deferred) {
    if(deferred) R_MEMSET(deferred,0,sizeof(*deferred));
    if(reply&&capacity) reply[0]=0;
    if(admin!=1) return error(reply,capacity,LB_FORBIDDEN);
    if(!reply||capacity<LB_HTTP_REPLY_MIN||!deferred) return error(reply,capacity,LB_UNAVAILABLE);
    if(!method||!path) return error(reply,capacity,LB_BAD_REQUEST);
    if(size>LB_HTTP_BODY_MAX) return error(reply,capacity,413);
    if(!core||!core->initialized||!core->adapter.now_ms||
       !hex(core->config.resident_build,64)||!hex(core->config.instance,32)) return error(reply,capacity,LB_UNAVAILABLE);
    if(!R_STRCMP(path,"/devloop-launch/status")) {
        if(R_STRCMP(method,"GET")) return error(reply,capacity,405);
        if(size) return error(reply,capacity,LB_BAD_REQUEST);
        uint64_t now=0;
        if(lb_status_clock(core,&now)!=LB_OK) return error(reply,capacity,LB_UNAVAILABLE);
        int count=R_SNPRINTF(reply,capacity,
            "{\"app\":\"Vita Resident Launch Broker\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"enabled\":%s,\"configured_enabled\":%s,\"blocked\":%s,\"now_ms\":%llu}",
            core->config.resident_build,core->config.instance,
            core->config.enabled&&!core->blocked?"true":"false",core->config.enabled?"true":"false",
            core->blocked?"true":"false",(unsigned long long)now);
        return count>=0&&(size_t)count<capacity ? 200 : error(reply,capacity,LB_UNAVAILABLE);
    }
    if(!R_STRCMP(path,"/devloop-launch")) {
        if(R_STRCMP(method,"POST")) return error(reply,capacity,405);
        LBRequest parsed;
        if(!request(body,size,&parsed)) return error(reply,capacity,LB_BAD_REQUEST);
        LBReceipt receipt={0};
        int code=lb_offer(core,&parsed,&receipt);
        if(code!=LB_ACCEPTED) return error(reply,capacity,code);
        if(!receipt_json(&receipt,reply,capacity)) return error(reply,capacity,LB_UNAVAILABLE);
        R_MEMCPY(deferred->attempt,receipt.attempt,sizeof(deferred->attempt));
        deferred->armed=1;
        return 202;
    }
    static const char prefix[]="/devloop-launch/";
    if(!R_STRNCMP(path,prefix,sizeof(prefix)-1)&&R_STRLEN(path)==sizeof(prefix)-1+32&&hex(path+sizeof(prefix)-1,32)) {
        if(R_STRCMP(method,"GET")) return error(reply,capacity,405);
        if(size) return error(reply,capacity,LB_BAD_REQUEST);
        LBAuth auth={0};
        auth.role=LB_ROLE_ADMIN;
        R_MEMCPY(auth.resident_build,core->config.resident_build,sizeof(auth.resident_build));
        R_MEMCPY(auth.instance,core->config.instance,sizeof(auth.instance));
        LBReceipt receipt={0};
        int code=lb_get(core,&auth,path+sizeof(prefix)-1,&receipt);
        if(code!=LB_OK) return error(reply,capacity,code);
        return receipt_json(&receipt,reply,capacity) ? 200 : error(reply,capacity,LB_UNAVAILABLE);
    }
    return error(reply,capacity,LB_NOT_FOUND);
}
