#!/bin/sh
set -eu
LB_TEST_OUTPUT=${LB_TEST_OUTPUT:-build/resident/launch-broker-host}
mkdir -p "$LB_TEST_OUTPUT"
LB_SANITIZERS=${LB_SANITIZERS:--fsanitize=address,undefined -fno-omit-frame-pointer}
cc -std=c11 -Wall -Wextra -Werror -pedantic -g $LB_SANITIZERS resident/launch_broker/core.c resident/launch_broker/test_core.c -o "$LB_TEST_OUTPUT/core-tests"
"$LB_TEST_OUTPUT/core-tests"
