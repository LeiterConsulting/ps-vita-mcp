#!/bin/sh
set -eu
mkdir -p build/resident
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -DR_BUILD_ID=\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\" resident/service.c resident/sha256.c resident/platform_host.c resident/pairing.c resident/pairing_json.c resident/pairing_io.c -o build/resident/host-server
python3 resident/test_service.py

cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Iresident resident/pairing.c resident/pairing_json.c resident/sha256.c resident/test_pairing.c -o build/resident/pairing-tests
build/resident/pairing-tests
