#!/bin/sh
set -eu
mkdir -p build/resident/autostart-host
AO_SANITIZERS=${AO_SANITIZERS:--fsanitize=address,undefined -fno-omit-frame-pointer}
# Intentional word splitting permits optional host compiler/sanitizer flags.
cc -std=c11 -Wall -Wextra -Werror -g $AO_SANITIZERS resident/autostart/core.c resident/autostart/test_core.c -o build/resident/autostart-host/core-tests
build/resident/autostart-host/core-tests
cc -std=c11 -Wall -Wextra -Werror -g $AO_SANITIZERS -DAO_PROBE_HOST -DCONTROL_BUILD_ID=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\" resident/autostart/probe.c resident/autostart/core.c resident/autostart/test_probe.c -o build/resident/autostart-host/probe-tests
build/resident/autostart-host/probe-tests
cc -std=c11 -Wall -Wextra -Werror -g $AO_SANITIZERS resident/autostart/test_platform.c resident/autostart/core.c resident/sha256.c -o build/resident/autostart-host/platform-tests
build/resident/autostart-host/platform-tests
