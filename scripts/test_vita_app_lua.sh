#!/bin/sh
# Build the generic app checker against the real shared sandbox, not system Lua.
set -eu
output=${1:-/output}
case "$output" in /output) ;; *) exit 2 ;; esac
mkdir -p "$output/lua"
for source in third_party/lua-5.4.9/src/*.c; do
    name=$(basename "$source" .c)
    case "$name" in lua|luac|linit|ldblib|liolib|loslib|loadlib|lcorolib) continue ;; esac
    cc -std=c11 -O1 -g -fsanitize=address,undefined -Ithird_party/lua-5.4.9/src \
        -c "$source" -o "$output/lua/$name.o"
done
ar rcs "$output/libdevloop_lua.a" "$output"/lua/*.o
cc -std=c11 -Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined \
    -Icommon -Idevloop -Ithird_party/lua-5.4.9/src \
    app_tools/lua_check.c devloop/core.c devloop/script_runtime.c devloop/sha256.c \
    tests/render_stub.c common/physics.c common/math_helpers.c \
    "$output/libdevloop_lua.a" -lm -o "$output/test_lua_check"
