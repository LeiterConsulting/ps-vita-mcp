#include "pairing_client.h"
#include "platform.h"
static int token_valid(const char *s) {
    if(!s||R_STRLEN(s)!=32)return 0;
    for(unsigned i=0;i<32;i++)if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f')))return 0;
    return 1;
}
static int lower(const char *a,const char *b) {
    while(*a&&*b){char c=*a++;if(c>='A'&&c<='Z')c+=32;if(c!=*b++)return 0;}return *a==*b;
}
int pc_call(const PCIO *io,unsigned port,const char admin[33],const char *path,const char *body,char out[PR_JSON_MAX]) {
    out[0]=0;
    if(!port||port>65535||!token_valid(admin)||R_STRNCMP(path,"/pairing/",9)||R_STRLEN(path)>64||!pr_json_valid(body,R_STRLEN(body))||R_STRLEN(body)>PR_REQUEST_MAX)return 0;
    for(const char *p=path;*p;p++)if(!((*p>='a'&&*p<='z')||*p=='/'))return 0;
    char request[1400],incoming[PR_JSON_MAX+1024];
    int size=R_SNPRINTF(request,sizeof(request),"POST %s HTTP/1.1\r\nHost: 127.0.0.1:%u\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %u\r\nConnection: close\r\n\r\n%s",path,port,admin,(unsigned)R_STRLEN(body),body);
    if(size<0||(unsigned)size>=sizeof(request))return 0;
    uint64_t deadline=io->mono()+1500;int fd=io->connect(port),status=0;
    if(fd<0){R_MEMSET(request,0,sizeof(request));return 0;}
    size_t sent=0,used=0;
    while(sent<(size_t)size&&io->mono()<deadline){int n=io->send(fd,request+sent,(size_t)size-sent);if(n>0&&(size_t)n<=(size_t)size-sent)sent+=(size_t)n;else if(n==-2)io->delay(5);else goto done;}
    R_MEMSET(request,0,sizeof(request));if(sent!=(size_t)size)goto done;
    /* Read to EOF; advertised length alone is not enough to accept extra bytes. */
    while(io->mono()<deadline){int n=io->recv(fd,incoming+used,sizeof(incoming)-1-used);if(n>0&&(size_t)n<sizeof(incoming)-used){used+=(size_t)n;if(used==sizeof(incoming)-1)goto done;}
        else if(n==-2)io->delay(5);else if(n==0)break;else goto done;}
    if(io->mono()>=deadline||!used)goto done;
    incoming[used]=0;for(size_t i=0;i<used;i++)if(!incoming[i])goto done;
    char *end=R_STRSTR(incoming,"\r\n\r\n"),*line=R_STRSTR(incoming,"\r\n");if(!end||!line||(size_t)(end-incoming)+4>1024)goto done;
    if(R_STRNCMP(incoming,"HTTP/1.1 ",9)||line-incoming<12||incoming[9]<'1'||incoming[9]>'5'||incoming[10]<'0'||incoming[10]>'9'||incoming[11]<'0'||incoming[11]>'9'||incoming[12]!=' ')goto done;
    int code=(incoming[9]-'0')*100+(incoming[10]-'0')*10+incoming[11]-'0';if(code>=300&&code<400)goto done;
    unsigned length=0;int has_length=0,has_type=0;char *body_start=end+4;line+=2;
    while(line<end){char *next=R_STRSTR(line,"\r\n");if(!next||next>end||*line==' '||*line=='\t')goto done;*next=0;char *colon=R_STRCHR(line,':');if(!colon)goto done;*colon++=0;while(*colon==' '||*colon=='\t')colon++;
        if(lower(line,"content-length")){if(has_length++||!*colon)goto done;for(char *p=colon;*p;p++){if(*p<'0'||*p>'9'||length>PR_JSON_MAX/10)goto done;length=length*10+(unsigned)(*p-'0');if(length>=PR_JSON_MAX)goto done;}}
        else if(lower(line,"content-type")){if(has_type++||!lower(colon,"application/json"))goto done;}
        else if(lower(line,"transfer-encoding")||lower(line,"location"))goto done;
        line=next+2;
    }
    if(!has_length||!has_type||used-(size_t)(body_start-incoming)!=length||!pr_json_valid(body_start,length))goto done;
    R_MEMCPY(out,body_start,length);out[length]=0;status=code;
done:
    io->close(fd);R_MEMSET(request,0,sizeof(request));R_MEMSET(incoming,0,sizeof(incoming));return status;
}
int pc_authorized(const PCIO *io,unsigned port,const char admin[33],const char token[33],int renew) {
    if(!token_valid(token))return 401;
    char body[96],reply[PR_JSON_MAX],app[32];uint64_t protocol=0;int authorized=0;
    R_SNPRINTF(body,sizeof(body),"{\"protocol\":1,\"token\":\"%s\"}",token);
    int code=pc_call(io,port,admin,renew?"/pairing/native/renew":"/pairing/native/validate",body,reply);
    R_MEMSET(body,0,sizeof(body));
    int good=code==200&&pr_json_string(reply,R_STRLEN(reply),"app",app,sizeof(app))&&!R_STRCMP(app,"Vita Companion Pairing")&&pr_json_uint(reply,R_STRLEN(reply),"protocol",&protocol)&&protocol==1&&pr_json_bool(reply,R_STRLEN(reply),"authorized",&authorized)&&authorized;
    R_MEMSET(reply,0,sizeof(reply));return good?200:code==401?401:503;
}
int pc_capture_allowed(const PCIO *io,unsigned port,const char admin[33]) {
    char reply[PR_JSON_MAX],app[32];uint64_t protocol=0;int allowed=0;
    int code=pc_call(io,port,admin,"/pairing/native/privacy","{\"protocol\":1}",reply);
    int good=code==200&&pr_json_string(reply,R_STRLEN(reply),"app",app,sizeof(app))&&!R_STRCMP(app,"Vita Companion Pairing")&&pr_json_uint(reply,R_STRLEN(reply),"protocol",&protocol)&&protocol==1&&pr_json_bool(reply,R_STRLEN(reply),"capture_allowed",&allowed)&&allowed;
    R_MEMSET(reply,0,sizeof(reply));return good;
}
