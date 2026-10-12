#!/bin/sh
set -eu
# Match vita_create_self(UNSAFE STRIPPED) from the pinned SDK's generated Ninja.
# A second conversion binds package bytes to the source-verified current ELF.
vita-elf-create -s build/devloop/vita_devloop build/devloop/vita_devloop-chain.velf
vita-make-fself -c build/devloop/vita_devloop-chain.velf build/devloop/vita_devloop-chain.self
cmp build/devloop/vita_devloop.velf build/devloop/vita_devloop-chain.velf
cmp build/devloop/vita_devloop.self build/devloop/vita_devloop-chain.self
printf '%s\n' 'PASS pinned SDK ELF -> STRIPPED VELF -> UNSAFE compressed SELF byte equality'
