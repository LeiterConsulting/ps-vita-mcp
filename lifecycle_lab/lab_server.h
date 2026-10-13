#ifndef VITA_LIFECYCLE_LAB_SERVER_H
#define VITA_LIFECYCLE_LAB_SERVER_H
#include "lab_core.h"
int lab_server_start(const LabCore *core);
void lab_server_tick(LabCore *core);
int lab_server_stop(void);
#endif
