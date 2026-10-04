#!/bin/sh
set -eu
mkdir -p build/resident/control
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -DRC_BOOT_HOST -DR_BUILD_ID=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\" resident/control/bootstrap_metadata.c resident/control/test_bootstrap_metadata.c -o build/resident/control/bootstrap-metadata-tests
build/resident/control/bootstrap-metadata-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -DRC_BOOT_HOST -DR_BUILD_ID=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\" resident/control/bootstrap_probe.c resident/control/test_bootstrap_probe.c -o build/resident/control/bootstrap-probe-tests
build/resident/control/bootstrap-probe-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/control/lease.c resident/control/test_lease.c -o build/resident/control/lease-tests
build/resident/control/lease-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/control/test_button_map.c -o build/resident/control/button-map-tests
build/resident/control/button-map-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/control/test_touch_activity.c -o build/resident/control/touch-activity-tests
build/resident/control/touch-activity-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/control/power_policy.c resident/control/test_power.c -o build/resident/control/power-tests
build/resident/control/power-tests
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g -Iresident resident/control/http.c resident/control/rle.c resident/control/power_policy.c resident/sha256.c resident/control/lease.c resident/control/platform_host.c -o build/resident/control/host-server
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -g resident/control/rle.c resident/control/test_rle.c -o build/resident/control/rle-tests
build/resident/control/rle-tests
python3 resident/control/test_service.py
python3 resident/control/test_rgb_codec.py
