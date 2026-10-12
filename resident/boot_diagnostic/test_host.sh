#!/bin/sh
set -eu
BD_TEST_OUTPUT=${BD_TEST_OUTPUT:-build/resident/boot-diagnostic-host}
mkdir -p "$BD_TEST_OUTPUT"
BD_SANITIZERS=${BD_SANITIZERS:--fsanitize=address,undefined -fno-omit-frame-pointer}
cc -std=c11 -Wall -Wextra -Werror -pedantic -g $BD_SANITIZERS resident/boot_diagnostic/test_platform.c -o "$BD_TEST_OUTPUT/platform-tests"
"$BD_TEST_OUTPUT/platform-tests"
