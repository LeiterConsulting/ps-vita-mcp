#include "api.h"
#include "test_proxy_platform.h"
#include <assert.h>

int module_start(SceSize size,const void *arg);
static char entry[4096],report[1600],report_path[160];
static unsigned calls,entry_size,report_size;
static int report_open_error,report_write_error,info_error,report_short,report_rename_error,published;
static unsigned char session_data[45];
static unsigned session_size,session_position;
static int session_close_error,pid,shell_guard;
int sceKernelGetProcessId(void) { return pid; }
int sceIoOpen(const char *path,int flags,int mode) {
    assert(mode==(0600|SCE_S_IRSYS|SCE_S_IWSYS) || mode==0);
    if(!strcmp(path,VI_SESSION_PATH)) { assert(flags==SCE_O_RDONLY && mode==0);return session_size?3:(int)0x80010002; }
    if(strstr(path,"/proxy-entry-")) {
        if(flags&SCE_O_TRUNC) entry_size=0;
        return 1;
    }
    assert(flags&SCE_O_EXCL);
    snprintf(report_path,sizeof(report_path),"%s",path);
    return report_open_error?report_open_error:2;
}
int sceIoRead(int fd,void *data,unsigned size) {
    assert(fd==3 && session_position<=session_size);
    unsigned n=session_size-session_position;if(n>size) n=size;
    memcpy(data,session_data+session_position,n);session_position+=n;return (int)n;
}
int sceIoWrite(int fd,const void *data,unsigned size) {
    if(fd==1) { assert(entry_size+size<sizeof(entry)); memcpy(entry+entry_size,data,size); entry_size+=size; entry[entry_size]=0; return (int)size; }
    assert(fd==2);
    if(report_write_error) return report_write_error;
    if(report_short) return (int)size-1;
    assert(size<sizeof(report)); memcpy(report,data,size); report[size]=0; report_size=size; return (int)size;
}
int sceIoClose(int fd) { assert(fd>=1 && fd<=3); return fd==3?session_close_error:0; }
int sceIoRename(const char *old_path,const char *new_path) {
    assert(strstr(old_path,".log.part") && !strstr(new_path,".part"));
    if(report_rename_error) return report_rename_error;
    published=1;return 0;
}
int viVersion(void) { calls++; return VI_ABI; }
int viInfo(VIInfo *out,unsigned size) {
    calls++; assert(size==sizeof(*out));
    if(info_error) return info_error;
    *out=(VIInfo){.magic=VI_MAGIC,.abi=VI_ABI,.size=sizeof(*out),.caller_before=pid,.caller_after=pid,.shell_pid=100,.guard_allowed=shell_guard,.tick_us=777};
    return 0;
}
int viBuildId(char *out,unsigned size) { calls++; if(size!=65) return VI_E_ARGUMENT; memcpy(out,VI_BUILD_ID,65); return 0; }
int viShellBuildId(char *out,unsigned size) { assert(size==65); calls++;if(shell_guard) { memcpy(out,VI_BUILD_ID,65);return 0; }return VI_E_DENIED; }
static void reset(void) {
    calls=entry_size=report_size=0; entry[0]=report[0]=report_path[0]=0;
    report_open_error=report_write_error=info_error=report_short=report_rename_error=published=0;
    session_size=session_position=0;session_close_error=0;pid=42;shell_guard=0;
}
static void shell_session(const VIArgs *args) {
    memcpy(session_data,args,sizeof(*args));session_size=sizeof(*args);pid=100;shell_guard=1;
}
int main(void) {
    VIArgs args={.magic=VI_ARGS_MAGIC,.mode=1,.run="0123456789abcdef0123456789abcdef"};
    reset(); assert(module_start(0,0)==0); assert(!calls && !report_size && strstr(entry,"Shell session record open result=0x80010002"));
    reset(); assert(module_start(43,&args)==0); assert(!calls && strstr(entry,"module entry args size result=0x0000002b"));
    reset(); args.run[3]='/'; assert(module_start(sizeof(args),&args)==0); assert(!calls && !report_path[0]); args.run[3]='3';
    reset(); args.mode=3; assert(module_start(sizeof(args),&args)==0); assert(!calls); args.mode=1;
    reset(); assert(module_start(sizeof(args),&args)==0); assert(calls==5 && report_size && strstr(report,"build_matched=1\n"));
    assert(strstr(report_path,"/0123456789abcdef0123456789abcdef/self.log.part")); assert(strstr(entry,"diagnostic finished"));assert(published);
    assert(strstr(report,"guard_result=0x80020008\n") && strstr(report,"invalid_size_result=0x80020005\n"));
    assert(viEntryComplete(entry,VI_BUILD_ID,args.run));
    assert(!viEntryComplete(entry,VI_BUILD_ID,"ffffffffffffffffffffffffffffffff"));
    assert(!viEntryComplete(entry,"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",args.run));
    assert(!viEntryComplete("\nbuild_id=",VI_BUILD_ID,args.run));
    reset(); args.mode=2; assert(module_start(sizeof(args),&args)==0); assert(strstr(report_path,"/shell.log")); args.mode=1;
    reset(); info_error=(int)0x80024001; assert(module_start(sizeof(args),&args)==0); assert(strstr(report,"info_result=0x80024001\n"));
    reset(); report_open_error=(int)0x8001000d; assert(module_start(sizeof(args),&args)==0); assert(!report_size && strstr(entry,"report open result=0x8001000d"));
    reset(); report_write_error=(int)0x8001001c; assert(module_start(sizeof(args),&args)==0); assert(!report_size && strstr(entry,"report write result=0x8001001c"));
    reset(); report_short=1; assert(module_start(sizeof(args),&args)==0); assert(!report_size && !published && strstr(entry,"incomplete report retained as part"));
    reset(); report_rename_error=(int)0x8001000d;assert(module_start(sizeof(args),&args)==0);assert(!published && strstr(entry,"report publish result=0x8001000d"));
    reset();shell_session(&args);assert(module_start(0,0)==0);assert(calls==5 && published && strstr(report,"user_pid=0x00000064\n") && strstr(report,"guard_matched=1\n"));
    assert(strstr(report_path,"/0123456789abcdef0123456789abcdef/shell.log.part") && viEntryComplete(entry,VI_BUILD_ID,args.run));
    reset();shell_session(&args);assert(module_start(0,(void *)1)==0);assert(published); /* Zero-size entry never dereferences a foreign pointer. */
    reset();shell_session(&args);session_size--;assert(module_start(0,0)==0);assert(!calls && !published && strstr(entry,"Shell session record rejected"));
    reset();shell_session(&args);session_size++;assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);session_data[0]^=1;assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);session_data[8]='/';assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);session_data[4]=2;assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);session_data[43]=1;assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);session_close_error=(int)0x80010005;assert(module_start(0,0)==0);assert(!calls && !published);
    reset();shell_session(&args);pid=42;shell_guard=0;assert(module_start(0,0)==0);assert(calls==2 && !published && strstr(entry,"Shell session caller rejected"));
    reset();shell_session(&args);shell_guard=0;assert(module_start(0,0)==0);assert(calls==2 && !published);
    reset();shell_session(&args);info_error=(int)0x80024001;assert(module_start(0,0)==0);assert(calls==2 && !published);
    puts("23 Inspector proxy argument, shared-session, caller guard, metadata and file-failure cases passed.");
    return 0;
}
