#ifndef VITA_RESIDENT_KEEP_AWAKE_PLATFORM_H
#define VITA_RESIDENT_KEEP_AWAKE_PLATFORM_H
#include <stdint.h>
uint64_t rkap_now(void);
int rkap_tick(void);
int rkap_listen(void);
int rkap_worker_start(void (*worker)(void));
int rkap_worker_join(void);
#ifndef __vita__
/* Host-only synthetic adapters, excluded from the Vita artifact. */
void rkap_host_config(unsigned port,const char *fixture_root);
int rkap_host_network_ready(void);
#endif
#endif
