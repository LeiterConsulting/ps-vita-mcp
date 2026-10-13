#ifndef VITA_LIFECYCLE_LAB_CORE_H
#define VITA_LIFECYCLE_LAB_CORE_H
#include <stddef.h>
#include <stdint.h>
#define LAB_TITLE "VMCP00001"
#define LAB_APP "Vita Native Lifecycle Lab"
#define LAB_PORT 17868
#define LAB_JSON_MAX 1536
#ifndef LAB_VERSION
#define LAB_VERSION "01.00"
#endif
#ifndef LAB_BUILD_ID
#define LAB_BUILD_ID "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#endif
#ifndef LAB_VARIANT
#define LAB_VARIANT 1
#endif
typedef struct {
    int32_t pid;
    char run[33];
    uint64_t frame,sampled_ms;
    uint32_t revision,checksum;
    int selftest_passed,exit_phase,exit_response_complete;
    uint32_t exit_expected_revision;
} LabCore;
int lab_init(LabCore *core,int32_t pid,const unsigned char nonce[16]);
void lab_tick(LabCore *core,uint64_t now);
int lab_status(const LabCore *core,char *out,size_t capacity,int acknowledged);
int lab_offer_exit(LabCore *core,const char *body,size_t bytes);
void lab_finish_exit(LabCore *core,int response_complete,int socket_closed);
int lab_exit_ready(const LabCore *core);
#endif
