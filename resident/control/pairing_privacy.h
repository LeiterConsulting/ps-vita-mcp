#ifndef VITA_PAIRING_PRIVACY_H
#define VITA_PAIRING_PRIVACY_H
/* Exact native process title, never a request-supplied title or PID allowlist. */
static inline int rc_pairing_process_allowed(int result,const char title[32]) {
    if(result<0)return 0;
    unsigned n=0;while(n<32&&title[n])n++;if(!n||n==32)return 0;
    static const char protected_title[]="CHRS00011";
    unsigned i=0;while(i<n&&i<sizeof(protected_title)-1&&title[i]==protected_title[i])i++;
    return !(i==n&&i==sizeof(protected_title)-1);
}
#endif
