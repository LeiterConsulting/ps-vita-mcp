#!/bin/sh
set -eu
mkdir -p build/native-launch
cc -std=c11 -Wall -Wextra -Werror -pedantic -g -DNL_HOST_TEST \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    resident/native_launch/native_launch.c resident/native_launch/test_native_launch.c \
    -o build/native-launch/policy-tests
build/native-launch/policy-tests
