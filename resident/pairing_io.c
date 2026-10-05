#include "pairing.h"
#include "platform.h"
#define PRIVATE_ROOT "ux0:data/vita-resident/private"
static void slot_path(unsigned slot,char path[128]) {R_SNPRINTF(path,128,PRIVATE_ROOT "/pairing-%u.bin",slot);}
static int exact(const char *path,void *out,size_t bytes) {
    int exists=r_pair_exists(path);if(exists<=0)return exists;
    uint64_t size;if(r_file_size(path,&size)<0||size!=bytes)return -1;
    int fd=r_open_read(path);if(fd<0)return -1;size_t used=0;int good=1;
    while(used<bytes){int n=r_read(fd,(char *)out+used,bytes-used);if(n<=0||(size_t)n>bytes-used){good=0;break;}used+=(unsigned)n;}
    if(r_close_file(fd)<0)good=0;
    return good?1:-1;
}
static int load_slot(unsigned slot,void *out,size_t bytes) {
    char path[128],part[128];slot_path(slot,path);R_SNPRINTF(part,sizeof(part),PRIVATE_ROOT "/pairing-%u.bin.part",slot);
    if(r_pair_exists(part)!=0)return -1;
    return exact(path,out,bytes);
}
static int store_slot(unsigned slot,const void *data,size_t bytes) {
    if(slot>1||bytes!=sizeof(PRRegistry))return -1;
    if(!r_directory_exists(PRIVATE_ROOT)&&r_dir(PRIVATE_ROOT)<0)return -1;
    char part[128],final[128];slot_path(slot,final);R_SNPRINTF(part,sizeof(part),PRIVATE_ROOT "/pairing-%u.bin.part",slot);
    if(r_pair_exists(part)!=0)return -1; /* Preserve unknown earlier commits for inspection. */
    int fd=r_open_write(part);if(fd<0)return -1;size_t used=0;int good=1;
    while(used<bytes){int n=r_write(fd,(const char *)data+used,bytes-used);if(n<=0||(size_t)n>bytes-used){good=0;break;}used+=(unsigned)n;}
    if(good&&r_pair_sync_file(fd)<0)good=0;
    if(r_close_file(fd)<0)good=0;
    if(!good)return -1;
    PRRegistry check;if(exact(part,&check,sizeof(check))!=1)return -1;
    unsigned difference=0;for(size_t i=0;i<bytes;i++)difference|=((const unsigned char *)&check)[i]^((const unsigned char *)data)[i];
    if(difference)return -1;
    int exists=r_pair_exists(final);if(exists<0||(exists&&r_pair_remove(final)<0)||r_rename(part,final)<0)return -1;
    if(r_pair_sync_device()<0)return -1;
    if(exact(final,&check,sizeof(check))!=1)return -1;
    difference=0;
    for(size_t i=0;i<bytes;i++)difference|=((const unsigned char *)&check)[i]^((const unsigned char *)data)[i];
    return difference?-1:0;
}
const PRIO *pr_platform_io(void) {
    static const PRIO io={r_pair_mono,r_pair_utc,r_pair_random,load_slot,store_slot};return &io;
}
