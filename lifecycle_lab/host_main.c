#include "lab_core.h"
#include "lab_platform.h"
#include "lab_server.h"
#include <signal.h>
#include <stdlib.h>
void lp_host_config(const char *folder,unsigned port);
void lp_host_event(const char *value);
static volatile sig_atomic_t stopped;
static void signal_stop(int value){(void)value;stopped=1;}
int main(int argc,char **argv){
    if(argc!=3)return 2;
    lp_host_config(argv[1],(unsigned)strtoul(argv[2],0,10));
    signal(SIGTERM,signal_stop);signal(SIGINT,signal_stop);
    unsigned char nonce[16];LabCore core;
    if(!lp_nonce(nonce)||!lab_init(&core,lp_pid(),nonce)||lab_server_start(&core)<0)return 3;
    while(!stopped&&!lab_exit_ready(&core)){lab_tick(&core,lp_now());lab_server_tick(&core);lp_delay(5);}
    if(lab_exit_ready(&core))lp_host_event("exit-main");
    return lab_server_stop()<0?4:0;
}
