#!/bin/sh
set -eu
mkdir -p build/resident/native_install
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -DNI_CORE_TEST \
  -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" \
  resident/native_install/test_core.c resident/native_install/service.c \
  resident/native_install/platform_host.c resident/sha256.c \
  -o build/resident/native_install/test-core
ASAN_OPTIONS=detect_leaks=1 build/resident/native_install/test-core
