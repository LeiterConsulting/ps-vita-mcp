#ifndef VITA_RESIDENT_KEEP_AWAKE_TRANSPORT_H
#define VITA_RESIDENT_KEEP_AWAKE_TRANSPORT_H
#include "power_platform.h"
#include <stddef.h>
#define RKT_CAPACITY 16u
#define RKT_MISSING UINT32_MAX
enum { RKT_FIRST_RECV,RKT_HEADERS,RKT_BODY,RKT_APPLY_BEFORE,RKT_APPLY_AFTER,RKT_FIRST_HEADER,RKT_COMPLETE,RKT_CLOSE,RKT_PHASES };
enum { RKT_PENDING,RKT_QUEUED,RKT_RECV_DEADLINE,RKT_SEND_DEADLINE,RKT_EOF,RKT_RECV_ERROR,RKT_SEND_ERROR,RKT_FRAMING,RKT_STOPPED,RKT_REGRESSION,RKT_FORMAT_ERROR };
enum { RKT_CLOCK_REGRESSION=1u,RKT_OFFSET_SATURATED=2u,RKT_APPLY_CALLED=4u,RKT_RESPONSE_QUEUED=8u,RKT_CLOSE_FAILED=16u };
typedef struct {
    uint64_t seq,accepted_ms,tick_count[2];
    uint32_t listener_generation,phase_ms[RKT_PHASES],bytes[3],would_block[2],revision[2],max_gap_ms,flags;
    int32_t apply_result,io_stage,io_result,io_errno,accept_result,accept_errno,close_result,close_errno;
    uint16_t http_status;
    uint8_t method,operation,outcome,reserved;
} RKTRecord;
_Static_assert(sizeof(RKTRecord)<=192,"bounded keep-awake transport record");
typedef struct {
    RKTRecord records[RKT_CAPACITY],current;
    uint64_t newest_seq,overwritten,diagnostic_reads,accepted,listen_attempts,listen_failures,accept_would_block,accept_failures;
    uint64_t listener_clock_ms,network_clock_ms,network_changes,last_step_ms,last_loss_ms;
    uint32_t count,next_index,listener_generation,max_gap_ms;
    RKASocketResult listener;
    RKANetworkResult network;
    RKANetworkResult last_loss;
    int current_active,clock_valid,network_valid,sequence_exhausted;
} RKTTransport;
void rkt_init(RKTTransport *trace);
void rkt_step(RKTTransport *trace,uint64_t now,RKANetworkResult network);
void rkt_begin(RKTTransport *trace,uint64_t now,uint64_t ticks,uint32_t revision,RKASocketResult accepted);
void rkt_mark(RKTTransport *trace,unsigned phase,uint64_t now);
void rkt_io(RKTTransport *trace,RKASocketResult result);
void rkt_finish(RKTTransport *trace,uint64_t now,uint64_t ticks,uint32_t revision,RKASocketResult closed,int diagnostic);
void rkt_listen_event(RKTTransport *trace,uint64_t now,int normalized,RKASocketResult result);
void rkt_accept_event(RKTTransport *trace,uint64_t now,int normalized,RKASocketResult result);
unsigned rkt_format_status(const RKTTransport *trace,const char instance_id[33],char *out,size_t size);
unsigned rkt_format_record(const RKTTransport *trace,const char instance_id[33],uint64_t seq,char *out,size_t size,int *http_status);
#endif
