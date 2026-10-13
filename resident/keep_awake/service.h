#ifndef VITA_RESIDENT_KEEP_AWAKE_SERVICE_H
#define VITA_RESIDENT_KEEP_AWAKE_SERVICE_H
int rka_start(const char token[33]);
int rka_stop(void);
int rka_active(void);
#endif
