#pragma once
#include "core.h"
bool dev_server_start(void);
void dev_server_apply_pending(DevCore *core);
void dev_server_publish(const DevCore *core);
void dev_server_address(char *out,size_t capacity);
bool dev_server_paired(void);
void dev_server_stop(void);
