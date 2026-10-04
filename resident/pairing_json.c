/* Bounded JSON/UTF-8 helpers shared by the actual service and native UI. */
#include "pairing.h"
#include "platform.h"
typedef struct { const char *p, *end; unsigned depth; } Parser;
static void white(Parser *p) { while(p->p<p->end && (*p->p==' '||*p->p=='\n'||*p->p=='\r'||*p->p=='\t')) p->p++; }
static int nibble(char c) { if(c>='0'&&c<='9') return c-'0'; if(c>='a'&&c<='f') return c-'a'+10; if(c>='A'&&c<='F') return c-'A'+10; return -1; }
int pr_utf8(const char *s,size_t n) {
    size_t i=0;
    while(i<n) {
        unsigned c=(unsigned char)s[i++],v,need;
        if(c<128) { if(c<32&&c!='\n'&&c!='\r'&&c!='\t') return 0; continue; }
        if(c>=0xc2&&c<=0xdf) {v=c&31;need=1;}
        else if(c>=0xe0&&c<=0xef) {v=c&15;need=2;}
        else if(c>=0xf0&&c<=0xf4) {v=c&7;need=3;}
        else return 0;
        if(n-i<need) return 0;
        unsigned count=need;
        while(need--) { c=(unsigned char)s[i++]; if((c&0xc0)!=0x80) return 0; v=(v<<6)|(c&63); }
        if((count==1&&v<128)||(count==2&&v<2048)||(count==3&&v<65536)||v>0x10ffff||(v>=0xd800&&v<=0xdfff)) return 0;
    }
    return 1;
}
static int unicode(Parser *p,unsigned *value) {
    if(p->end-p->p<4) return 0;
    unsigned v=0;
    for(unsigned i=0;i<4;i++) {int x=nibble(*p->p++);if(x<0)return 0;v=(v<<4)|(unsigned)x;}
    if(v>=0xd800&&v<=0xdbff) {
        if(p->end-p->p<6||p->p[0]!='\\'||p->p[1]!='u')return 0;
        p->p+=2;unsigned low=0;
        for(unsigned i=0;i<4;i++){int x=nibble(*p->p++);if(x<0)return 0;low=(low<<4)|(unsigned)x;}
        if(low<0xdc00||low>0xdfff)return 0;
        v=0x10000+((v-0xd800)<<10)+(low-0xdc00);
    } else if(v>=0xdc00&&v<=0xdfff)return 0;
    *value=v;return 1;
}
static int string(Parser *p,char *out,size_t cap) {
    if(p->p==p->end||*p->p++!='"')return 0;
    size_t used=0;
    while(p->p<p->end) {
        unsigned c=(unsigned char)*p->p++;unsigned char bytes[4];size_t n=1;
        if(c=='"') {if(out){if(used>=cap)return 0;out[used]=0;}return 1;}
        if(c<32)return 0;
        if(c=='\\') {
            if(p->p==p->end)return 0;
            c=(unsigned char)*p->p++;
            if(c=='u') {
                if(!unicode(p,&c)||!c)return 0;
                if(c<128)bytes[0]=(unsigned char)c;
                else if(c<2048){bytes[0]=0xc0|(c>>6);bytes[1]=0x80|(c&63);n=2;}
                else if(c<65536){bytes[0]=0xe0|(c>>12);bytes[1]=0x80|((c>>6)&63);bytes[2]=0x80|(c&63);n=3;}
                else{bytes[0]=0xf0|(c>>18);bytes[1]=0x80|((c>>12)&63);bytes[2]=0x80|((c>>6)&63);bytes[3]=0x80|(c&63);n=4;}
            } else {
                if(c=='b')c=8;else if(c=='f')c=12;else if(c=='n')c=10;else if(c=='r')c=13;else if(c=='t')c=9;
                else if(c!='"'&&c!='\\'&&c!='/')return 0;
                bytes[0]=(unsigned char)c;
            }
        } else bytes[0]=(unsigned char)c;
        if(out){if(used+n>=cap)return 0;R_MEMCPY(out+used,bytes,n);}used+=n;
    }
    return 0;
}
static int value(Parser *p);
static int compound(Parser *p,char close) {
    if(++p->depth>4)return 0;
    int object=close=='}';p->p++;white(p);
    if(p->p<p->end&&*p->p==close){p->p++;p->depth--;return 1;}
    for(;;) {
        if(object){if(!string(p,0,0))return 0;white(p);if(p->p==p->end||*p->p++!=':')return 0;}
        if(!value(p))return 0;
        white(p);if(p->p==p->end)return 0;
        char c=*p->p++;if(c==close){p->depth--;return 1;}if(c!=',')return 0;white(p);
    }
}
static int value(Parser *p) {
    white(p);if(p->p==p->end)return 0;
    if(*p->p=='{')return compound(p,'}');
    if(*p->p=='[')return compound(p,']');
    if(*p->p=='"')return string(p,0,0);
    for(unsigned i=0;i<3;i++){const char *t=i==0?"true":i==1?"false":"null";size_t n=R_STRLEN(t);if((size_t)(p->end-p->p)>=n&&!R_STRNCMP(p->p,t,n)){p->p+=n;return 1;}}
    if(*p->p=='-')p->p++;
    if(p->p==p->end)return 0;
    if(*p->p=='0')p->p++;else{if(*p->p<'1'||*p->p>'9')return 0;while(p->p<p->end&&*p->p>='0'&&*p->p<='9')p->p++;}
    if(p->p<p->end&&*p->p=='.'){p->p++;const char *start=p->p;while(p->p<p->end&&*p->p>='0'&&*p->p<='9')p->p++;if(start==p->p)return 0;}
    if(p->p<p->end&&(*p->p=='e'||*p->p=='E')){p->p++;if(p->p<p->end&&(*p->p=='+'||*p->p=='-'))p->p++;const char *start=p->p;while(p->p<p->end&&*p->p>='0'&&*p->p<='9')p->p++;if(start==p->p)return 0;}
    return 1;
}
static int lookup(const char *json,size_t n,const char *key,const char **start,const char **end) {
    if(!n||n>PR_JSON_MAX)return 0;
    Parser p={json,json+n,0};white(&p);if(p.p==p.end||*p.p++!='{')return 0;
    int found=0;white(&p);if(p.p<p.end&&*p.p=='}')p.p++;
    else for(;;) {
        char name[128];if(!string(&p,name,sizeof(name)))return 0;white(&p);if(p.p==p.end||*p.p++!=':')return 0;
        white(&p);const char *a=p.p;if(!value(&p))return 0;
        if(key&&!R_STRCMP(name,key)){if(found++)return 0;*start=a;*end=p.p;}
        white(&p);if(p.p==p.end)return 0;char c=*p.p++;if(c=='}')break;if(c!=',')return 0;white(&p);
    }
    white(&p);return p.p==p.end&&(key?found:1);
}
int pr_json_valid(const char *json,size_t n) {const char *a=0,*b=0;return pr_utf8(json,n)&&lookup(json,n,0,&a,&b);}
int pr_json_string(const char *json,size_t n,const char *key,char *out,size_t cap) {
    const char *a=0,*b=0;if(!lookup(json,n,key,&a,&b))return 0;Parser p={a,b,0};return string(&p,out,cap)&&p.p==b;
}
int pr_json_uint(const char *json,size_t n,const char *key,uint64_t *out) {
    const char *a=0,*b=0;if(!lookup(json,n,key,&a,&b)||a==b)return 0;uint64_t v=0;
    for(;a<b;a++){if(*a<'0'||*a>'9'||v>(UINT64_MAX-9)/10)return 0;v=v*10+(unsigned)(*a-'0');}*out=v;return 1;
}
int pr_json_bool(const char *json,size_t n,const char *key,int *out) {
    const char *a=0,*b=0;if(!lookup(json,n,key,&a,&b))return 0;
    if(b-a==4&&!R_STRNCMP(a,"true",4)){*out=1;return 1;}
    if(b-a==5&&!R_STRNCMP(a,"false",5)){*out=0;return 1;}return 0;
}
int pr_json_object_at(const char *json,size_t n,const char *key,unsigned index,char *out,size_t capacity) {
    const char *a=0,*b=0;if(!lookup(json,n,key,&a,&b)||*a!='[')return 0;
    Parser p={a+1,b,0};white(&p);
    for(unsigned i=0;p.p<p.end&&*p.p!=']';i++) {
        const char *start=p.p;if(*start!='{'||!value(&p))return 0;
        if(i==index){size_t size=(size_t)(p.p-start);if(size>=capacity)return 0;R_MEMCPY(out,start,size);out[size]=0;return 1;}
        white(&p);if(p.p==p.end||*p.p!=',')return 0;p.p++;white(&p);
    }return 0;
}
int pr_quote(char *out,size_t cap,const char *text) {
    size_t used=0;if(cap<3)return 0;
    out[used++]='"';
    for(const unsigned char *p=(const unsigned char *)text;*p;p++) {
        if(*p=='"'||*p=='\\'){if(used+2>=cap)return 0;
    out[used++]='\\';out[used++]=(char)*p;}
        else if(*p<32){if(used+6>=cap)return 0;int n=R_SNPRINTF(out+used,cap-used,"\\u%04x",*p);if(n!=6)return 0;used+=6;}
        else{if(used+1>=cap)return 0;
    out[used++]=(char)*p;}
    }
    if(used+2>cap)return 0;
    out[used++]='"';out[used]=0;return 1;
}
