#ifndef VITA_RESIDENT_FILES_H
#define VITA_RESIDENT_FILES_H
#include "platform.h"
#define RF_PAGE 32
#define RF_OFFSET_MAX 1000
#define RF_READ_MAX 16384
typedef struct { int status,binary; size_t length; } RFResult;
/* Administrator-only, canonical managed paths. No mutation or arbitrary roots. */
void rf_request(const char *path,char *json,size_t capacity,unsigned char *data,
                size_t data_capacity,uint64_t deadline,RFResult *result);
#endif
