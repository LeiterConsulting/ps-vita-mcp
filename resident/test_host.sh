#!/bin/sh
set -eu
mkdir -p build/resident
sh resident/build_host.sh --launch-fixture
sh resident/keep_awake/test_host.sh
python3 resident/test_keep_awake_integration.py
python3 resident/test_service.py
python3 resident/test_files_service.py
python3 resident/test_launch_service.py
python3 resident/test_native_http.py
sh resident/launch_broker/test_http.sh
sh resident/launch_broker/test_native_host.sh
sh resident/launch_broker/test_store.sh
sh resident/native_launch/test_host.sh
sh resident/native_install/test_host.sh

cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Iresident resident/pairing.c resident/pairing_json.c resident/sha256.c resident/test_pairing.c -o build/resident/pairing-tests
build/resident/pairing-tests
