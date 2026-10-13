#include "transport.h"
#include "../platform.h"
#include <limits.h>
#define U64(x) ((unsigned long long)(x))
static void increment(uint64_t *value) { if(*value<UINT64_MAX) ++*value; }
static uint32_t bounded(uint64_t value) { return value>=UINT32_MAX?UINT32_MAX-1:(uint32_t)value; }
void rkt_init(RKTTransport *trace) { R_MEMSET(trace,0,sizeof(*trace));trace->network.state=-1;trace->last_loss.state=-1; }
void rkt_step(RKTTransport *trace,uint64_t now,RKANetworkResult network) {
    if(trace->clock_valid) {
        if(now<trace->last_step_ms) { if(trace->current_active) trace->current.flags|=RKT_CLOCK_REGRESSION; }
        else {
            uint32_t gap=bounded(now-trace->last_step_ms);
            if(gap>trace->max_gap_ms) trace->max_gap_ms=gap;
            if(trace->current_active&&gap>trace->current.max_gap_ms) trace->current.max_gap_ms=gap;
        }
    }
    trace->last_step_ms=now;trace->clock_valid=1;
    if(!trace->network_valid||network.result!=trace->network.result||network.state!=trace->network.state) {
        if(trace->network_valid) increment(&trace->network_changes);
        trace->network_clock_ms=now;trace->network=network;trace->network_valid=1;
        if(network.result<0||network.state!=3) { trace->last_loss=network;trace->last_loss_ms=now; }
    }
}
void rkt_begin(RKTTransport *trace,uint64_t now,uint64_t ticks,uint32_t revision,RKASocketResult accepted) {
    increment(&trace->accepted);R_MEMSET(&trace->current,0,sizeof(trace->current));trace->current_active=1;
    RKTRecord *record=&trace->current;record->accepted_ms=now;record->tick_count[0]=ticks;record->revision[0]=revision;
    record->listener_generation=trace->listener_generation;record->accept_result=accepted.result;record->accept_errno=accepted.error;
    for(unsigned i=0;i<RKT_PHASES;i++) record->phase_ms[i]=RKT_MISSING;
}
void rkt_mark(RKTTransport *trace,unsigned phase,uint64_t now) {
    if(!trace->current_active||phase>=RKT_PHASES||trace->current.phase_ms[phase]!=RKT_MISSING) return;
    RKTRecord *record=&trace->current;
    if(now<record->accepted_ms) { record->flags|=RKT_CLOCK_REGRESSION;return; }
    uint64_t delta=now-record->accepted_ms;
    if(delta>=UINT32_MAX) record->flags|=RKT_OFFSET_SATURATED;
    record->phase_ms[phase]=bounded(delta);
}
void rkt_io(RKTTransport *trace,RKASocketResult result) {
    if(!trace->current_active) return;
    trace->current.io_stage=result.stage;trace->current.io_result=result.result;trace->current.io_errno=result.error;
}
void rkt_finish(RKTTransport *trace,uint64_t now,uint64_t ticks,uint32_t revision,RKASocketResult closed,int diagnostic) {
    RKTRecord *record=&trace->current;rkt_mark(trace,RKT_CLOSE,now);
    record->tick_count[1]=ticks;if(!(record->flags&RKT_APPLY_CALLED)) record->revision[1]=revision;
    record->close_result=closed.result;record->close_errno=closed.error;
    if(closed.result<0) record->flags|=RKT_CLOSE_FAILED;
    if(diagnostic) increment(&trace->diagnostic_reads);
    else if(trace->newest_seq<UINT64_MAX) {
        record->seq=++trace->newest_seq;trace->records[trace->next_index]=*record;
        trace->next_index=(trace->next_index+1)%RKT_CAPACITY;
        if(trace->count<RKT_CAPACITY) trace->count++;else increment(&trace->overwritten);
        if(trace->newest_seq==UINT64_MAX) trace->sequence_exhausted=1;
    }
    trace->current_active=0;
}
void rkt_listen_event(RKTTransport *trace,uint64_t now,int normalized,RKASocketResult result) {
    increment(&trace->listen_attempts);if(normalized<0) increment(&trace->listen_failures);
    else if(trace->listener_generation<UINT32_MAX) trace->listener_generation++;
    /* Reopening must not erase the error that required recovery before the PC
       can retrieve it. Keep the last failure, or the initial successful setup. */
    if(normalized<0||result.result<0||trace->listener.result>=0) { trace->listener_clock_ms=now;trace->listener=result; }
}
void rkt_accept_event(RKTTransport *trace,uint64_t now,int normalized,RKASocketResult result) {
    if(normalized==-1&&result.stage==RKA_STAGE_ACCEPT) { increment(&trace->accept_would_block);return; }
    if(normalized<0) { increment(&trace->accept_failures);trace->listener_clock_ms=now;trace->listener=result; }
}
unsigned rkt_format_status(const RKTTransport *trace,const char instance_id[33],char *out,size_t size) {
    uint64_t oldest=trace->count?trace->newest_seq-trace->count+1:0;
    int n=R_SNPRINTF(out,size,
        "{\"app\":\"Vita Resident Keep Awake Transport\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"status\":200,"
        "\"capacity\":16,\"record_bytes\":%u,\"count\":%u,\"oldest_seq\":\"%016llx\",\"newest_seq\":\"%016llx\","
        "\"overwritten\":%llu,\"diagnostic_reads\":%llu,\"accepted\":%llu,\"listener_generation\":%u,"
        "\"listen_attempts\":%llu,\"listen_failures\":%llu,\"accept_would_block\":%llu,\"accept_failures\":%llu,"
        "\"listener\":{\"clock_ms\":%llu,\"stage\":%d,\"result\":%d,\"errno\":%d,\"close_result\":%d,\"close_errno\":%d},"
        "\"network\":{\"result\":%d,\"state\":%d,\"changes\":%llu,\"clock_ms\":%llu,\"max_gap_ms\":%u,\"last_loss_result\":%d,\"last_loss_state\":%d,\"last_loss_ms\":%llu},"
        "\"sequence_exhausted\":%s,\"resource_sampling\":false}",R_BUILD_ID,instance_id,(unsigned)sizeof(RKTRecord),trace->count,
        U64(oldest),U64(trace->newest_seq),U64(trace->overwritten),U64(trace->diagnostic_reads),U64(trace->accepted),trace->listener_generation,
        U64(trace->listen_attempts),U64(trace->listen_failures),U64(trace->accept_would_block),U64(trace->accept_failures),U64(trace->listener_clock_ms),
        trace->listener.stage,trace->listener.result,trace->listener.error,trace->listener.close_result,trace->listener.close_error,
        trace->network.result,trace->network.state,U64(trace->network_changes),U64(trace->network_clock_ms),trace->max_gap_ms,
        trace->last_loss.result,trace->last_loss.state,U64(trace->last_loss_ms),trace->sequence_exhausted?"true":"false");
    return n>0&&(size_t)n<size?(unsigned)n:0;
}
unsigned rkt_format_record(const RKTTransport *trace,const char instance_id[33],uint64_t seq,char *out,size_t size,int *http_status) {
    const RKTRecord *record=0;
    for(unsigned i=0;i<trace->count;i++) if(trace->records[i].seq==seq&&seq) { record=&trace->records[i];break; }
    int n;*http_status=record?200:404;
    if(!record) {
        uint64_t oldest=trace->count?trace->newest_seq-trace->count+1:0;
        n=R_SNPRINTF(out,size,"{\"app\":\"Vita Resident Keep Awake Transport\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"status\":404,\"seq\":\"%016llx\",\"error\":%u}",R_BUILD_ID,instance_id,U64(seq),seq&&seq<oldest?2u:1u);
    } else n=R_SNPRINTF(out,size,
        "{\"app\":\"Vita Resident Keep Awake Transport\",\"protocol\":1,\"resident_build_id\":\"%s\",\"instance_id\":\"%s\",\"status\":200,"
        "\"seq\":\"%016llx\",\"listener_generation\":%u,\"accepted_ms\":%llu,\"method\":%u,\"operation\":%u,"
        "\"phase_ms\":[%u,%u,%u,%u,%u,%u,%u,%u],\"bytes\":[%u,%u,%u],\"would_block\":[%u,%u],\"revision\":[%u,%u],"
        "\"apply_result\":%d,\"http_status\":%u,\"outcome\":%u,\"io_stage\":%d,\"io_result\":%d,\"io_errno\":%d,"
        "\"accept_result\":%d,\"accept_errno\":%d,\"close_result\":%d,\"close_errno\":%d,\"tick_count\":[%llu,%llu],\"max_gap_ms\":%u,\"flags\":%u}",
        R_BUILD_ID,instance_id,U64(record->seq),record->listener_generation,U64(record->accepted_ms),(unsigned)record->method,(unsigned)record->operation,
        record->phase_ms[0],record->phase_ms[1],record->phase_ms[2],record->phase_ms[3],record->phase_ms[4],record->phase_ms[5],record->phase_ms[6],record->phase_ms[7],
        record->bytes[0],record->bytes[1],record->bytes[2],record->would_block[0],record->would_block[1],record->revision[0],record->revision[1],
        record->apply_result,(unsigned)record->http_status,(unsigned)record->outcome,record->io_stage,record->io_result,record->io_errno,
        record->accept_result,record->accept_errno,record->close_result,record->close_errno,U64(record->tick_count[0]),U64(record->tick_count[1]),record->max_gap_ms,record->flags);
    return n>0&&(size_t)n<size?(unsigned)n:0;
}
