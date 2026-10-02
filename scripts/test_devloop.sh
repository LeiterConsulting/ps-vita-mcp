#!/bin/sh
set -eu
mkdir -p build/host evidence/devloop
sh scripts/build_host_lua.sh
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Icommon tests/test_physics.c common/physics.c common/math_helpers.c -lm -o build/host/test_physics
build/host/test_physics
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Icommon -Idevloop -Ithird_party/lua-5.4.9/src tests/test_devloop.c devloop/core.c devloop/script_runtime.c devloop/sha256.c tests/render_stub.c common/physics.c common/math_helpers.c build/host/libdevloop_lua.a -lm -o build/host/test_devloop
build/host/test_devloop
cc -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter -fsanitize=address,undefined -g -Icommon -Idevloop -Itests -Ithird_party/lua-5.4.9/src tests/test_server_vita_host.c devloop/core.c devloop/script_runtime.c devloop/sha256.c tests/render_stub.c common/physics.c common/math_helpers.c build/host/libdevloop_lua.a -pthread -lm -o build/host/test_server_vita_host
build/host/test_server_vita_host
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Icommon -Idevloop -Ithird_party/lua-5.4.9/src tests/test_script_runtime.c devloop/core.c devloop/script_runtime.c devloop/sha256.c tests/render_stub.c common/physics.c common/math_helpers.c build/host/libdevloop_lua.a -lm -o build/host/test_script_runtime
build/host/test_script_runtime
