#!/bin/sh
set -eu
mkdir -p build/resident-keep-awake
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
    resident/keep_awake/policy.c resident/keep_awake/test_policy.c \
    -o build/resident-keep-awake/policy-test
ASAN_OPTIONS=detect_leaks=1 build/resident-keep-awake/policy-test
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
    -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" \
    resident/keep_awake/transport.c resident/keep_awake/test_transport.c \
    -o build/resident-keep-awake/transport-test
ASAN_OPTIONS=detect_leaks=1 build/resident-keep-awake/transport-test
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -pthread \
    -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" \
    resident/keep_awake/policy.c resident/keep_awake/service.c resident/keep_awake/transport.c \
    resident/keep_awake/power_platform_host.c resident/keep_awake/fixture.c \
    -o build/resident-keep-awake/host-server
python3 resident/keep_awake/test_http.py
python3 resident/keep_awake/test_transport.py
