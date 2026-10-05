#!/bin/sh
set -eu
mkdir -p build/workbench/target
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Icommon workbench/target/protocol.c workbench/target/telemetry.c workbench/target/test_target.c -o build/workbench/target/host-tests
build/workbench/target/host-tests
