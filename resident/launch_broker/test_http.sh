#!/bin/sh
set -eu
LB_HTTP_TEST_OUTPUT=${LB_HTTP_TEST_OUTPUT:-build/resident/launch-broker-http}
mkdir -p "$LB_HTTP_TEST_OUTPUT"
cc -std=c11 -Wall -Wextra -Werror -pedantic -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    resident/launch_broker/core.c resident/launch_broker/http.c resident/launch_broker/test_http.c \
    -o "$LB_HTTP_TEST_OUTPUT/http-tests"
"$LB_HTTP_TEST_OUTPUT/http-tests"
