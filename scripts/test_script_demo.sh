#!/bin/sh
set -eu
output=${1:-build/host/session-demo}
case "$output" in build/host/session-demo|build/host/session-demo/*) ;; *) exit 2 ;; esac
mkdir -p "$output/lua"
# Match the shared sandbox's pinned Lua source set and sanitizer flags. Keep this
# fixture's objects separate from other host tests and native package outputs.
for source in third_party/lua-5.4.9/src/*.c; do
    name=$(basename "$source" .c)
    case "$name" in lua|luac|linit|ldblib|liolib|loslib|loadlib|lcorolib) continue ;; esac
    cc -std=c11 -O1 -g -fsanitize=address,undefined -Ithird_party/lua-5.4.9/src -c "$source" -o "$output/lua/$name.o"
done
ar rcs "$output/libdevloop_lua.a" "$output"/lua/*.o
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g \
    -Icommon -Idevloop -Ithird_party/lua-5.4.9/src \
    tests/script_demo_runtime.c devloop/core.c devloop/script_runtime.c devloop/sha256.c \
    tests/render_stub.c common/physics.c common/math_helpers.c "$output/libdevloop_lua.a" \
    -lm -o "$output/test_script_demo"
"$output/test_script_demo" "$output/steady.lua" "$output/swift.lua" "$output/runtime-report.json"
