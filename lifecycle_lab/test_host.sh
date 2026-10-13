#!/bin/sh
set -eu
mkdir -p build/native-lab-host
flags='-std=c11 -Wall -Wextra -Werror -pedantic -g -fsanitize=address,undefined -fno-omit-frame-pointer'
cc $flags lifecycle_lab/lab_core.c lifecycle_lab/test_core.c -o build/native-lab-host/core-tests
build/native-lab-host/core-tests
cc $flags lifecycle_lab/lab_core.c lifecycle_lab/lab_server.c lifecycle_lab/lab_platform_host.c lifecycle_lab/host_main.c \
    -pthread -o build/native-lab-host/http-server
python3 lifecycle_lab/test_http.py
python3 lifecycle_lab/test_pc_contract.py
