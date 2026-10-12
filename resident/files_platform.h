#ifndef VITA_RESIDENT_FILES_PLATFORM_H
#define VITA_RESIDENT_FILES_PLATFORM_H
#include "platform.h"

/* Managed inbox only. Directory enumeration is serialized by the service.
   Entries are observations, not a snapshot; unsupported kinds remain kind 0. */
typedef struct {
    char name[256];
    int kind; /* 1: regular file, 2: directory, 0: unsupported */
    uint64_t bytes;
} RFEntry;
/* Opens return -1 for absent/unsupported paths, -2 for I/O failures. */
int rf_dir_open(const char *attempt); /* NULL: inbox; otherwise 32 lowercase hex */
int rf_dir_next(int handle,RFEntry *entry); /* 1: entry, 0: end, -1: error */
int rf_dir_close(int handle);
int rf_open(const char *attempt,const char *leaf,uint64_t *size);
int rf_seek(int fd,uint64_t offset);
int rf_size(int fd,uint64_t *size);
int rf_close(int fd);
#ifndef __vita__
void rf_host_root(const char *root);
#endif
#endif
