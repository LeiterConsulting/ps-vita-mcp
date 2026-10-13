#!/bin/sh
# Shared host-only dependency list for Resident and two-service Control tests.
set -eu
mkdir -p build/resident
case ${1:-} in
    '') launch_test_flag='' ;;
    --launch-fixture) launch_test_flag='-DLB_HOST_SERVICE_TEST_ENABLED' ;;
    *) exit 2 ;;
esac
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g $launch_test_flag \
    -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" \
    resident/service.c resident/sha256.c resident/platform_host.c resident/pairing.c resident/files.c resident/files_platform_host.c \
    resident/pairing_json.c resident/pairing_io.c resident/launch_broker/core.c \
    resident/launch_broker/http.c resident/launch_broker/store.c \
    resident/launch_broker/native_host.c resident/launch_broker/service.c \
    resident/native_install/service.c resident/native_install/platform_host.c \
    resident/keep_awake/policy.c resident/keep_awake/service.c resident/keep_awake/power_platform_host.c -pthread \
    -o build/resident/host-server
