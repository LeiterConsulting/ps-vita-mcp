# Native installation and lifecycle

Status date: October 12 2026. The corrected Resident 0.1.5 is now boot-loaded
and its exact device binary is verified after a user-confirmed normal boot.
Its fresh native instance is unblocked and reports the installer ready, with
Promoter unloaded. Four fixed-Lab install/launch/evaluate/graceful-exit cycles
across two native builds passed on hardware, including repeated reinstall and
a changed-build redeploy, with successful read-only reconciliation. Same-build
journal durability after reboot remains pending. Accepted Resident 0.1.4 is
retained for rollback; DevLoop 01.04 remains installed. Host simulations and an
ARM build do not establish Vita acceptance.

The [dated validation record](native-lifecycle-validation.json) pins the exact
source, Resident plugin, lab package and 27 passing host groups. It records
staging, the four passed native cycles across two builds and the remaining hardware gates separately.

This path removes routine file-manager installation and manual app opening
for an explicitly owned test title. Resident receives a normalized homebrew
package, verifies its files, submits one platform installation, launches the
fixed title, and observes its native identity. The lab provides authenticated
status and cooperative exit. The PC orchestrator journals each operation and can repeat the cycle for its
exact candidate. Build scripts can produce a subsequent candidate for a new
hash-bound preview and execution plan.

The first owned target is **Vita Lifecycle Lab**, project `lifecycle_lab`, title
`VMCP00001`, HTTP port `17868`. This qualification does not overwrite the
working DevLoop package. It does not authorize arbitrary titles, forceful
process termination, kernel loading, uninstallation or boot configuration
changes. The old `/devloop-launch` broker stays disabled.

## October 12 native promotion incident

The first Resident 0.1.5 build was boot-loaded on the test Vita:
`eb99ab853a5c3f974458f5df7126601421560d9dd8b1018eb8f60305eb60c7d6`,
plugin SHA-256 `1e3494e9af1a72705bf31e940c09a878f93db1e4d86ce3dd33a9b0625e0f168b`.
The operator confirmed a normal boot. Eleven staged update/rollback files passed
two complete readbacks, preserving administrator pairing, the 0.1.4, 0.1.3 and
0.1.2 rollback plugins and both withdrawn-experiment disable markers. A fresh
actual MCP session exposed all 36 tools, and all eight fixed Lab staging files
passed hash verification.

One native `scePromoterUtilityPromotePkgWithRif(path, 0)` call returned
`0x80871012` after successful module load/initialization, borrowed Shell PAF and
idle-policy checks. Its retained receipt is `unknown` and blocks further native
mutations under that original build; it has not been replayed. FTP inspection found no installed Lab
directory. This does not prove that the platform made no other changes or
establish the error's cause.

The corrected Resident 0.1.5 now uses the shorter promotion workspace
`ux0:data/vita-resident/p/<operation-id>` while preserving full build identities
in staging and metadata. The operator confirmed normal boot, and the exact
device binary matches build
`67d04a52b80660628907321d34825f4ce7d77a5ccf4354a478d4e3ae5d72a637`,
plugin SHA-256 `33c3ef76d746da8e3a0e853b2b6afb5634d138971a782dfc0c516c14cc3d2c97`.
Its fresh native instance `9204e9d29165a6240627fd0b670e273c` is unblocked and
reports the installer ready, with Promoter unloaded. Twenty-two retained files
passed two readbacks, including the original unknown receipt. Pairing,
rollback plugins and withdrawn-experiment disable markers remain preserved.
The corrected full 27-group host suite passed independently.

This fresh build has not reclassified or replayed the original operation.
Keep the original uncertain attempt and its evidence; do not reset its guard
or repeat it. Accepted 0.1.4 is retained as a historical rollback baseline;
DevLoop 01.04 remains installed separately.

### Corrected build: single-cycle hardware pass

After the file manager was closed, one controlled native cycle passed on the
corrected build. Installation submitted exactly one platform call; its native,
operation and cleanup results were zero and stored-file verification passed.
The fixed-title launch returned zero. Lifecycle Lab reported exact build
`f839e2d027e60e3d74db37884132ffc5e23203566c11b82482d5d2daee53ad8b`,
PID `539467` and a run identity matching independent Resident inventory.
Frames advanced from 31 to 101; the deterministic self-test passed with checksum
`2727420034`. Cooperative exit and two independent process-absence observations
passed, leaving `native_lab_left_running: false`.

A subsequent separate MCP GET-only reconciliation timed out. A read-only CLI
reconciliation of the same completed job then succeeded at 18:51 UTC, recovering
the original receipts, complete stage and ready, unblocked guard with Promoter
unloaded. It performed zero device mutations and did not replay the completed
job. The timeout remains retained as a recovered read-only transport event.

The generated header was unchanged and accepted for this exact fixed package.
Success after shortening the promotion path supports that diagnostic hypothesis;
it does not establish a verified meaning for `0x80871012` or qualify arbitrary
headers.

### Same-candidate redeployment pass

A new plan then completed two additional cycles of the same exact Lab package.
All three total cycles passed native installation, fixed-title launch, exact
build/runtime checks, deterministic evaluation, cooperative exit and verified
process absence. Each cycle had a distinct native PID/run identity, and every
installation returned zero native, operation and cleanup results. The separate
two-cycle job and its read-only reconciliation passed without file-manager
installation or manual app opening between cycles. The first single-cycle job
took 34.659 seconds; the two-cycle job took 90.317 seconds on the test connection.
These observed durations are not a performance guarantee.

Repeated same-candidate reinstall is qualified for this exact Resident and Lab
package.

### Different-build redeployment pass

A fourth cycle installed and launched Lab 01.01, variant 2, through a new
hash-bound plan. It passed native installation, exact runtime identity,
deterministic evaluation, cooperative exit and verified process absence;
read-only reconciliation also passed. Native, operation and cleanup results
were zero and stored-file verification passed. Its native build was
`b52ad43ee9846c5f1698b1a5dfb048959cb782638589a0e36234925091d170d6`,
VPK SHA-256 `f08486b610756ac19b74470a2fcfe611afb90e9ffc0756e5e5edce7c1c31347d`
(127,750 bytes). Runtime PID `733533`, run
`1ae95baf9510d77a44f3e9990444b174` and variant 2 matched the candidate;
frames advanced from 24 to 97 and self-test passed. The job took 33.395 seconds
on the test connection and finished with the Lab absent.

These four cycles across two native builds qualify install, launch, evaluation,
cooperative exit and redeploy for the dedicated owned Lab under this exact
Resident build. A normal reboot with unchanged configuration is the next
same-build journal-durability check; no result is claimed yet. Arbitrary apps,
DevLoop generalization, automatic Control bootstrap, interrupted native
operations or power cuts, broader devices and full autonomous platform
operation remain unqualified.

## Native boundary

Administrator authentication is required for every `/native-lifecycle`
request. Phone inspection credentials do not authorize this namespace.
Requests bind the current Resident build and random native instance, an
immutable stage manifest, a fresh operation ID and a short native-clock
deadline. A separate retained attempt records each install or launch.

Receipt TTLs are at most 30 seconds, but native freshness checks also require
no more than five seconds from the issued native-clock timestamp through
preparation and the final pre-dispatch check. Copying, hashing and preparation
must finish within that tighter window. A larger package can therefore be
refused before any platform effect even while its receipt TTL is valid. The
small Lab packages above are qualified; full 8 MiB package operation is not.

Only these eight relative paths can be staged:

| Index | File |
| --- | --- |
| 0 | `eboot.bin` |
| 1 | `sce_sys/param.sfo` |
| 2 | `sce_sys/icon0.png` |
| 3 | `sce_sys/livearea/contents/bg.png` |
| 4 | `sce_sys/livearea/contents/startup.png` |
| 5 | `sce_sys/livearea/contents/template.xml` |
| 6 | `LICENSE` |
| 7 | `sce_sys/package/head.bin` |

Each file is at most 8 MiB; their total is at most 16 MiB. The desktop validates
the VPK, SFO, SELF and exact build report before normalization. It generates
the homebrew package header without copying a third-party installer template.
The Vita verifies streaming hashes, complete stored readbacks, package identity
and available storage before promotion. An existing title must match a
previously verified manifest owned by this service. An unrelated installed
title is a refusal.

Staging, attempts and owned package history are retained. There is no automatic
garbage collection. One Resident build retains at most 32 stages and 64 native
operations; one PC plan runs one to three cycles of its exact candidate.
Ownership records are scoped to the Resident build and are not silently
migrated during a service upgrade. A timeout or disconnect can leave a retained partial file
or an uncertain operation; inspect the original stage or attempt. Never repeat
a mutation solely because its reply was lost. Restart recovery does not replay
installation or launch.

## Install and launch policy

`idle_shell_only` requires bounded successful app enumeration with no running
app and two valid Shell-state samples without reported events or overlay.
The adapter checks this policy again immediately before submitting the fixed
URI `psgm:play?titleid=VMCP00001` to the platform. These observations are not
atomic display ownership or protected-UI attestation; the corresponding
verification flags remain false.

Promoter initialization happens only for an explicit accepted install, never
at boot, service initialization or a status read. PAF must already be loaded.
Resident tracks modules and initialization it owns and does not unload a
borrowed module. An uncertain still-running promotion retains its resources.
The native operation result is checked separately from the SDK call result.

Installation and launch intents are committed before platform calls. Native
receipts distinguish refusal, submission, observed completion and uncertainty.
A successful launch call alone does not establish a running candidate. The PC
also requires exact runtime build/title/PID/run identity, advancing frames and
independent Resident inventory agreement.

## Cooperative shutdown and iteration

The lab reads the existing private Resident administrator credential from
`ux0:data/vita-resident/bridge.cfg`; the credential is absent from the VPK and
public repository. Exit binds the exact runtime identity and revision. The
network worker acknowledges and closes the connection before the main thread
cleans up and exits. Installation cannot proceed while the owned process is
still present or its absence cannot be established.

The PC holds a Workbench session lock and writes durable intent records before
mutations. Its preview pins the candidate and current Resident identity. After
execution, read-only reconciliation uses the original operation IDs. An
unresolved install, launch, exit or identity change stops the cycle. Rollback
is not automatic. A separately planned redeployment can select a retained
owned candidate only after verified process absence. A failed native self-test
in a verified owned runtime triggers cooperative exit and returns
`failed_checks`; it does not redeploy that failed candidate. An ownership
mismatch or uncertain effect stops further mutations.

## Hardware qualification

Build the lab with `Build-NativeLab.ps1` and Resident with `Build-Resident.ps1`.
Use `vita_workbench_native_preview` with the exact lab VPK SHA-256 and a
bounded cycle count. Supply its unchanged `plan` and `plan_sha256` to
`vita_workbench_native_execute`. Inspect an interrupted job with
`vita_workbench_native_reconcile` and its original `job_id`. The same flow is
available through `python -m workbench.native_lifecycle preview`, `execute`
and `reconcile`; execution accepts a saved preview plan and its canonical hash.

The replacement Resident requires one physical configuration copy and normal
reboot. It replaces only the existing Resident line in `ur0:tai/config.txt`,
preserves the administrator credential and keeps the exact accepted plugin
and prior configuration as rollback. The withdrawn Autostart and boot-resource
diagnostic experiments remain disabled.

After a normal boot, first inspect module availability, native identity and
the retained store. Close other apps and leave LiveArea open for the native
lab trial. Qualify initial installation, fixed-title launch, exact runtime
observation, graceful exit and verified absence, then a second installation
and launch with a different build. Reboot durability, interrupted operations
and longer repeated cycles need separate evidence. Generalizing this adapter
to DevLoop or other project titles follows those lab results.
