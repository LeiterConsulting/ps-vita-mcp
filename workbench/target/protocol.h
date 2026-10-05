#ifndef WORKBENCH_TARGET_PROTOCOL_H
#define WORKBENCH_TARGET_PROTOCOL_H
#include <stddef.h>
int target_authorize(char *text,size_t size,const char token[33]);
#endif
