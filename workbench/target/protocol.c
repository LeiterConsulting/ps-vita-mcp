#include "protocol.h"
#include <string.h>
#include <strings.h>
int target_authorize(char *text,size_t size,const char token[33]) {
    if(!size||memchr(text,0,size)) return 400;
    char *end=strstr(text,"\r\n\r\n");if(!end||end+4!=text+size) return 400;
    *end=0;char *line=strstr(text,"\r\n");if(!line) return 400;*line=0;
    if(strcmp(text,"GET /status HTTP/1.1")) return 404;
    unsigned seen=0,length_seen=0;
    for(char *p=line+2;*p;) {
        char *next=strstr(p,"\r\n");if(next) *next=0;
        if(*p==' '||*p=='\t') return 400;
        char *colon=strchr(p,':');if(!colon) return 400;*colon++=0;while(*colon==' '||*colon=='\t') colon++;
        if(!strcasecmp(p,"authorization")) {
            if(seen++||strlen(colon)!=39||strncmp(colon,"Bearer ",7)) return 401;
            unsigned difference=0;for(unsigned i=0;i<32;i++) difference|=(unsigned char)colon[i+7]^(unsigned char)token[i];if(difference) return 401;
        } else if(!strcasecmp(p,"transfer-encoding")||!strcasecmp(p,"expect")) return 400;
        else if(!strcasecmp(p,"content-length")&&(length_seen++||strcmp(colon,"0"))) return 400;
        if(!next) break;
        p=next+2;
    }return seen==1?200:401;
}
