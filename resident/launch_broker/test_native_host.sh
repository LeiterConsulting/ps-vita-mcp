#!/bin/sh
set -eu
LB_NATIVE_TEST_OUTPUT=${LB_NATIVE_TEST_OUTPUT:-build/resident/launch-broker-native-host}
mkdir -p "$LB_NATIVE_TEST_OUTPUT"
LB_NATIVE_SANITIZERS=${LB_NATIVE_SANITIZERS:--fsanitize=address,undefined -fno-omit-frame-pointer}
cc -std=c11 -Wall -Wextra -Werror -pedantic -g -DLB_NATIVE_HOST $LB_NATIVE_SANITIZERS \
    resident/launch_broker/native_vita.c resident/launch_broker/test_native.c \
    -o "$LB_NATIVE_TEST_OUTPUT/native-tests"
"$LB_NATIVE_TEST_OUTPUT/native-tests"
