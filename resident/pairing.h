#ifndef VITA_COMPANION_PAIRING_H
#define VITA_COMPANION_PAIRING_H
#include <stddef.h>
#include <stdint.h>
#define PR_DAYS_SECONDS UINT64_C(7776000)
#define PR_MAX_PHONES 8
#define PR_JSON_MAX 4096
#define PR_REQUEST_MAX 1024
typedef struct {
    char client_id[33], credential_id[33], digest[65], label[65];
    uint64_t last_seen, expires;
    uint8_t revoked, reserved[7];
} __attribute__((packed)) PRPhone;
typedef struct {
    uint32_t magic, version, bytes, count;
    uint64_t generation, high_water;
    char device_id[33], reserved[7];
    PRPhone phones[PR_MAX_PHONES];
    char checksum[65];
} __attribute__((packed)) PRRegistry;
typedef struct {
    uint64_t (*mono)(void);
    int (*utc)(uint64_t *seconds);
    int (*random)(void *out, size_t bytes);
    int (*load)(unsigned slot, void *out, size_t bytes); /* 0 absent, 1 read, -1 error */
    int (*store)(unsigned slot, const void *data, size_t bytes); /* atomic/readback checked */
} PRIO;
typedef struct {
    unsigned phase, wrong;
    char request_id[33], client_id[33], nonce[33], label[65], code_digest[65];
    char credential_id[33], recovery_token[33];
    uint64_t deadline, utc_deadline;
} PRPending;
typedef struct {
    PRIO io;
    PRRegistry registry;
    PRPending pending;
    int ready, active_slot, ui_open;
    uint64_t ui_deadline, ui_seen, cooldown, rate_start;
    unsigned rate_count;
    unsigned resident_port, control_port;
    char resident_build[65], control_build[65];
} PRState;
int pr_init(PRState *s, const PRIO *io, unsigned resident_port, unsigned control_port, const char *build);
int pr_auth(PRState *s, const char *token, int renew); /* 200 / 401 / 503 */
int pr_dispatch(PRState *s, const char *method, const char *path, int loopback, int admin,
                const char *bearer, const char *body, size_t bytes, char out[PR_JSON_MAX]);
int pr_json_string(const char *json, size_t bytes, const char *key, char *out, size_t capacity);
int pr_json_uint(const char *json, size_t bytes, const char *key, uint64_t *out);
int pr_json_bool(const char *json, size_t bytes, const char *key, int *out);
int pr_json_object_at(const char *json,size_t bytes,const char *key,unsigned index,char *out,size_t capacity);
int pr_json_valid(const char *json, size_t bytes);
int pr_utf8(const char *text, size_t bytes);
int pr_quote(char *out, size_t capacity, const char *text);
void pr_sha(const void *data, size_t bytes, char out[65]);
void pr_code_digest(const char request[33], const char client[33], const char nonce[33], const char code[7], char out[65]);
int pr_random_code(int (*random)(void *, size_t), char out[7]);
const PRIO *pr_platform_io(void);
#endif
