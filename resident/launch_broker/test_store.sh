#!/bin/sh
set -eu
LB_STORE_TEST_OUTPUT=${LB_STORE_TEST_OUTPUT:-build/resident/launch-broker-store-host}
mkdir -p "$LB_STORE_TEST_OUTPUT"
LB_STORE_SANITIZERS=${LB_STORE_SANITIZERS:--fsanitize=address,undefined -fno-omit-frame-pointer}
cc -std=c11 -Wall -Wextra -Werror -pedantic -g $LB_STORE_SANITIZERS \
    -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" \
    resident/launch_broker/core.c resident/launch_broker/store.c resident/sha256.c \
    resident/launch_broker/test_store.c -o "$LB_STORE_TEST_OUTPUT/store-tests"
"$LB_STORE_TEST_OUTPUT/store-tests"
