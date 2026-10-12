/* Synthetic POSIX adapter for actual service/HTTP integration fixtures only.
   This file must never be compiled into the Vita module. It contains no SDK. */
#ifdef __vita__
#error "launch_broker/native_host.c is a host-only synthetic test adapter"
#endif
#include "native.h"
#include "../platform.h"

static int identity_state;
static char identity[33];

int lb_native_instance(char out[33]) {
    if(!out) return 0;
    out[0]=0;
    int state=__atomic_load_n(&identity_state,__ATOMIC_ACQUIRE);
    if(state==2) { R_MEMCPY(out,identity,sizeof(identity));return 1; }
    int expected=0;
    if(!__atomic_compare_exchange_n(&identity_state,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))
        return 0;
    unsigned char bytes[16]={0};unsigned nonzero=0;
    /* Removing this fixture marker later cannot retry the retained failure. */
    if(r_pair_exists("ux0:data/vita-resident/fault-launch-rng")!=0 ||
       r_pair_random(bytes,sizeof(bytes))!=0) {
        __atomic_store_n(&identity_state,-1,__ATOMIC_RELEASE);return 0;
    }
    for(unsigned i=0;i<sizeof(bytes);i++) nonzero|=bytes[i];
    if(!nonzero) { __atomic_store_n(&identity_state,-1,__ATOMIC_RELEASE);return 0; }
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<sizeof(bytes);i++) {
        identity[2*i]=hex[bytes[i]>>4];identity[2*i+1]=hex[bytes[i]&15u];
    }
    identity[32]=0;
    __atomic_store_n(&identity_state,2,__ATOMIC_RELEASE);
    R_MEMCPY(out,identity,sizeof(identity));return 1;
}

uint64_t lb_native_now(void *ctx) { (void)ctx;return r_pair_mono(); }

LBLaunchResult lb_native_launch(void *ctx) {
    (void)ctx;
    LBLaunchResult refused={0,LB_NATIVE_LAUNCH_UNQUALIFIED};
#if defined(LB_HOST_SERVICE_TEST_ENABLED)
    /* Both compile-time test scope and a local fixture marker are necessary.
       The actual service separately requires fixture-enable-launch. */
    if(r_pair_exists("ux0:data/vita-resident/fixture-launch-success")!=1) return refused;
    int fd=r_open_write("ux0:data/vita-resident/fixture-launch-called");
    if(fd<0) return refused;
    static const char marker[]=LB_TITLE "\n";
    int written=r_write(fd,marker,sizeof(marker)-1);
    int synced=written==(int)sizeof(marker)-1?r_pair_sync_file(fd):-1;
    int closed=r_close_file(fd);
    if(written!=(int)sizeof(marker)-1 || synced!=0 || closed!=0) return refused;
    LBLaunchResult synthetic={1,0};return synthetic;
#else
    return refused;
#endif
}

int lb_native_inventory(char *reply,size_t capacity) {
    if(!reply||!capacity) return -1;
    int count=R_SNPRINTF(reply,capacity,
        "{\"app\":\"Vita Resident Launch Inventory\",\"protocol\":1,\"host_fixture\":true,"
        "\"sampled_ms\":%llu,\"available\":true,\"snapshot_atomic\":false,"
        "\"foreground_verified\":false,\"protected_ui_verified\":false,"
        "\"native_submission_enabled\":false,\"entries\":[],\"entries_reported\":0,"
        "\"launch_policy\":\"unqualified_disabled\"}",(unsigned long long)lb_native_now(0));
    if(count<0||(size_t)count>=capacity) { reply[0]=0;return -1; }
    return count;
}
