#!/bin/sh
set -eu
mkdir -p build/host/vita-app-native
cc -std=c11 -Wall -Wextra -Werror -pedantic -g \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  app_slot/templates/app_sim.c app_slot/templates/test_app.c \
  -lm -o build/host/vita-app-native/app-tests
build/host/vita-app-native/app-tests
