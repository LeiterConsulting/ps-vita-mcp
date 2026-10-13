/* Deterministic width/sentinel/exhaustion boundaries, without clock sleeps. */
#include "transport.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static const char instance[]="11111111111111111111111111111111";

static void finish_record(RKTTransport *trace,uint64_t now,int diagnostic) {
    RKASocketResult accepted={0},closed={0};
    accepted.result=42;accepted.stage=RKA_STAGE_ACCEPT;
    closed.stage=RKA_STAGE_CLOSE;
    rkt_begin(trace,now,10,7,accepted);
    rkt_finish(trace,now+1,11,8,closed,diagnostic);
}

static void maximum_width(RKTTransport *trace) {
    memset(trace,0xff,sizeof(*trace));
    trace->count=RKT_CAPACITY;trace->next_index=0;trace->current_active=0;
    trace->clock_valid=1;trace->network_valid=1;trace->sequence_exhausted=0;
    trace->listener.stage=INT32_MIN;trace->listener.result=INT32_MIN;
    trace->listener.error=INT32_MIN;trace->listener.close_result=INT32_MIN;
    trace->listener.close_error=INT32_MIN;
    trace->network.result=INT32_MIN;trace->network.state=INT32_MIN;
    trace->last_loss.result=INT32_MIN;trace->last_loss.state=INT32_MIN;
    for(unsigned i=0;i<RKT_CAPACITY;i++) {
        RKTRecord *record=&trace->records[i];
        record->seq=UINT64_MAX-RKT_CAPACITY+1+i;
        record->apply_result=INT32_MIN;record->io_stage=INT32_MIN;
        record->io_result=INT32_MIN;record->io_errno=INT32_MIN;
        record->accept_result=INT32_MIN;record->accept_errno=INT32_MIN;
        record->close_result=INT32_MIN;record->close_errno=INT32_MIN;
    }
}

static void formatting_bounds(int emit_json) {
    RKTTransport trace,before;maximum_width(&trace);before=trace;
    char reply[1400];int code=0;
    unsigned size=rkt_format_status(&trace,instance,reply,sizeof(reply));
    assert(size>0&&size<sizeof(reply)&&size==strlen(reply));
    assert(reply[size]=='\0'&&reply[0]=='{'&&reply[size-1]=='}');
    if(emit_json) puts(reply);
    assert(!memcmp(&before,&trace,sizeof(trace)));
    assert(!rkt_format_status(&trace,instance,reply,size));
    assert(!memcmp(&before,&trace,sizeof(trace)));
    size=rkt_format_record(&trace,instance,UINT64_MAX,reply,sizeof(reply),&code);
    assert(code==200&&size>0&&size<sizeof(reply)&&size==strlen(reply));
    assert(reply[size]=='\0'&&reply[0]=='{'&&reply[size-1]=='}');
    if(emit_json) puts(reply);
    assert(!memcmp(&before,&trace,sizeof(trace)));
    assert(!rkt_format_record(&trace,instance,UINT64_MAX,reply,size,&code));
    assert(!memcmp(&before,&trace,sizeof(trace)));
    size=rkt_format_record(&trace,instance,0,reply,sizeof(reply),&code);
    assert(code==404&&size>0&&size<sizeof(reply));
    assert(strstr(reply,"\"error\":1"));
}

static void phase_sentinels_are_unambiguous(void) {
    RKTTransport trace;rkt_init(&trace);
    RKASocketResult accepted={0};accepted.result=42;
    rkt_begin(&trace,10000,0,0,accepted);
    for(unsigned i=0;i<RKT_PHASES;i++) assert(trace.current.phase_ms[i]==RKT_MISSING);
    rkt_mark(&trace,RKT_FIRST_RECV,10000);
    assert(trace.current.phase_ms[RKT_FIRST_RECV]==0); /* A reached zero is valid. */
    rkt_mark(&trace,RKT_FIRST_RECV,10099);
    assert(trace.current.phase_ms[RKT_FIRST_RECV]==0); /* First occurrence wins. */
    rkt_mark(&trace,RKT_HEADERS,9999);
    assert(trace.current.flags&RKT_CLOCK_REGRESSION);
    assert(trace.current.phase_ms[RKT_HEADERS]==RKT_MISSING);
    rkt_mark(&trace,RKT_BODY,10000+UINT64_C(0xffffffff));
    assert(trace.current.flags&RKT_OFFSET_SATURATED);
    assert(trace.current.phase_ms[RKT_BODY]==UINT32_MAX-1);
    assert(trace.current.phase_ms[RKT_APPLY_BEFORE]==RKT_MISSING);
}

static void diagnostic_reads_and_sequence_exhaustion(void) {
    RKTTransport trace;rkt_init(&trace);
    for(unsigned i=0;i<RKT_CAPACITY+1;i++) finish_record(&trace,100+i*10,0);
    assert(trace.count==16&&trace.newest_seq==17&&trace.overwritten==1);
    RKTRecord retained[RKT_CAPACITY];memcpy(retained,trace.records,sizeof(retained));
    finish_record(&trace,1000,1);
    assert(trace.count==16&&trace.newest_seq==17&&trace.overwritten==1);
    assert(trace.diagnostic_reads==1&&!memcmp(retained,trace.records,sizeof(retained)));

    rkt_init(&trace);trace.newest_seq=UINT64_MAX-1;trace.accepted=UINT64_MAX;
    finish_record(&trace,1000,0);
    assert(trace.accepted==UINT64_MAX&&trace.newest_seq==UINT64_MAX);
    assert(trace.count==1&&trace.sequence_exhausted);
    retained[0]=trace.records[0];
    finish_record(&trace,2000,0);
    assert(trace.newest_seq==UINT64_MAX&&trace.count==1&&trace.overwritten==0);
    assert(!memcmp(&retained[0],&trace.records[0],sizeof(RKTRecord)));
    trace.diagnostic_reads=UINT64_MAX;
    finish_record(&trace,3000,1);
    assert(trace.diagnostic_reads==UINT64_MAX);
}

int main(int argc,char **argv) {
    if(argc==2&&!strcmp(argv[1],"--max-json")) { formatting_bounds(1);return 0; }
    assert(argc==1);
    phase_sentinels_are_unambiguous();diagnostic_reads_and_sequence_exhaustion();
    formatting_bounds(0);
    puts("Resident transport width/sentinel/exhaustion boundaries: PASS");
    return 0;
}
