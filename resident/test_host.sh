#!/bin/sh
set -eu
mkdir -p build/resident
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/service.c resident/sha256.c resident/platform_host.c -o build/resident/host-server
python3 resident/test_service.py
