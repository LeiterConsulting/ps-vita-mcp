#!/bin/sh
set -eu
mkdir -p build/host/lua
for source in third_party/lua-5.4.9/src/*.c; do
    name=$(basename "$source" .c)
    case "$name" in lua|luac|linit|ldblib|liolib|loslib|loadlib|lcorolib) continue ;; esac
    cc -std=c11 -O1 -g -fsanitize=address,undefined -Ithird_party/lua-5.4.9/src -c "$source" -o "build/host/lua/$name.o"
done
ar rcs build/host/libdevloop_lua.a build/host/lua/*.o
