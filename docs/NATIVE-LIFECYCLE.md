# Native installation and lifecycle

Status date: October 13, 2026. Resident **0.1.7** is running with its exact build
verified. Current-build installation, redeployment and an uninterrupted
keeper-protected native application cycle remain unqualified; the power and
transport trials made no native app effects or POST replays.

Current PC source passed one **90-second hold at one-minute standby** with
eight renewals, no retries and confirmed end at revision 41, tick count 377.
After 75 quiet seconds and one unreachable status GET, the operator confirmed
usual normal automatic sleep before touching the Vita. This qualifies the
bounded hold and explicit-release sleep, separately from retained earlier
failures. Full suspension, physical TTL sleep and broad reliability remain open.

Renewal-only preflight recovery passed 58 lease, eight deadline and 26
transport-client tests. It allows one eligible GET retry while preserving
ownership, revision and lifetime checks; POSTs are never replayed and native
effect freshness reads remain strict. The current hold needed zero retries.
Its localhost/in-memory controlled harness passed. The controlled Vita attempt
stopped when the fresh upstream GET timed out: no renewal POST, exactly two
begin/end POSTs and confirmed end at revision 43, tick 399. The relay used a
4.5-second upstream budget versus a five-second local budget. Later
unchecked/checked Wi-Fi power-saving comparisons stopped on read-only baselines
with zero POSTs. The comparison is inconclusive; the operator restored the
original checked setting. Controlled recovery remains unqualified. Current host stdio/file-MCP checks and
all 41 native-lifecycle PC tests passed.
[CI run 38456106601](https://github.com/LeiterConsulting/ps-vita-mcp/actions/runs/38456106601)
passed all 33 host groups at code commit `2a32d08`; all 34 required artifact
files were independently size/hash-verified. This later documentation-only
checkpoint preserves that PC and native code; CI ran on the named code commit.
These host results do not qualify a native application
cycle. Native plugin bytes are unchanged; restart the PC MCP for registered
jobs to load the new keeper.
[Current transport evidence](RESIDENT-TRANSPORT.md).

The native runner starts its keeper after local package/plan validation, plan
claim, durable payload archiving and the initial idle status read. Those steps
are outside its lease. The command wrapper separately protects one host command;
planning, build tooling and Lua sessions do not automatically share a lease.
A continuous work session needs future explicit injection or borrowing from
one outer owner; independent nested keepers would contend for ownership.
[Current lease coverage](RESIDENT-KEEP-AWAKE.md#what-is-protected-automatically).

The historical 0.1.6 results are recorded below. The corrected Resident 0.1.5 previously
passed boot loading and exact device-binary verification after a user-confirmed normal boot.
Its fresh native instance was unblocked and reported the installer ready, with
Promoter unloaded. Five fixed-Lab install/launch/evaluate/graceful-exit cycles
across two native builds passed on hardware, including repeated reinstall,
a changed-build redeploy and redeployment after reboot. All four execution jobs
passed read-only reconciliation. Same-build journal durability also passed after
a normal reboot, with GET-only verification and no replay. Accepted Resident
0.1.4 is retained for rollback; DevLoop 01.04 remains installed. Host simulations
and an ARM build do not establish Vita acceptance.

The separate [Make Vita App workflow](MAKE-VITA-APP.md) adds an application-module
wrapper for this single owned development slot. It preserves the pristine Lab
baseline and authenticates application health through the existing lifecycle
envelope. Two generated Native Paddle builds passed registered-MCP lifecycle
cycles and read-only reconciliation, including a changed-source redeploy. These
results are recorded separately from the five baseline cycles above; the wrapper
does not enable arbitrary titles or establish visual/physical acceptance.

The [dated validation record](native-lifecycle-validation.json) pins the exact
source, Resident plugin, lab package and 27 passing host groups. It records
staging, the five passed native cycles across two builds and the remaining
hardware gates separately.

<a id="resident-016-hardware-check"></a>

## Historical Resident 0.1.6 hardware check

That keep-awake candidate passed normal boot and bounded power tests;
it does not inherit 0.1.5 installation acceptance. A native execution at
21:52:59 UTC verified all eight files in stage
`14ee990ff41641eda253a9cef7a4f498`, then stopped at `install_rejected` after ten
mutation submissions: stage creation, eight uploads and one install request.
No launch followed. The lease ended with zero renewals and no keeper errors.
The client at that point discarded the rejection body and status, so the exact
runtime reason is unknown. Follow-up GETs found the service unblocked and
idle-ready, with no active operation; original operation
`e9004f231a9c43869dcc6b564cab68b9` returned 404, with no claim observed.

The source requires an existing title to have a verified ownership receipt for
the current Resident build. Its 0.1.5 receipts are not silently migrated to
0.1.6. That documented barrier is a likely explanation for this refusal;
the runtime did not retain the exact reason. The new PC diagnostic patch keeps
only whitelisted status/reason/category values and passed all 41 host tests,
including six targeted real-HTTP tests. The fresh root rerun passed all 41 tests
in 67.202 seconds.

A separate launch-only probe (local receipt:
`evidence/workbench/native-launch-only-20261012T215805Z-bf7f2d34/report.json`)
submitted launch `fc9670653c214fc683bf6d3b4254687f` once and made no install
submission. PID `996399`, run `0b8c607779092318d6c4e38485832015`, passed 25
self-test samples; frames advanced from 14 to 620 with checksum `2727420034`.
Graceful exit was acknowledged at revision 2. A final fresh keep-awake GET
timeout left the original result **unconfirmed**, after one renewal, with
immediate lease cleanup also unconfirmed. No mutation was replayed.

Later GET-only reconciliation confirmed two stable idle/closed-Lab observations
and an inactive native lease at revision 37, reason `lease_expired`. Those
observations prove later absence while retaining the original unconfirmed job
result. Launch, self-test and acknowledged exit have runtime evidence; an
uninterrupted keeper-protected cycle, installation and redeployment under
Resident 0.1.6 remain unqualified.

A second launch-only probe (local receipt:
`evidence/workbench/native-launch-only-20261012T220725Z-a8fa3025/report.json`)
at 22:07:25 UTC stopped on `TimeoutError` before starting its keep-awake lease or
submitting a native mutation. Its result remained blocked and keeper end was
`not_started`; it does not add launch or cycle acceptance.

A subsequent install-diagnostic preparation stopped on its first preview GET
with `LifecycleTransport`, before a plan claim, journal, lease start or native
mutation. No new install was submitted, so the historical rejection's exact
cause remains unknown. The operator-facing result is a separate unstarted
preparation; its private no-mutation record is retained outside public evidence.


Separately, one controlled live proxy fault passed exact-owner reconciliation
of an accepted renewal whose reply was deliberately dropped, with three total
POSTs (start, renewal, end), tick progress and confirmed end without replay.
That proof qualifies lease reply-loss handling only; it does not qualify native
installation or physical Wi-Fi interruption. A separate 0.1.6 90-second
hold at restored one-minute standby ended cleanly, followed by operator-confirmed
normal automatic sleep. That passes sleep after explicit lease end; physical
sleep after TTL expiry, full suspension and lease cancellation remain pending.
A later 90-second continuity trial passed seven renewals and confirmed end while
Power-button/display sleep and wake worked normally. Renewal continued, so full
suspension and cancellation during it were not established.

A physical Wi-Fi interruption stopped the PC keeper without replay; the original
hold remains `failed_or_interrupted`. After the operator manually reconnected
Wi-Fi, two GET-only observations found both services responding on the same
build/instance, the original lease inactive at revision 66, ownership cleared
and tick count 559 stable. The retained reason was `listener_lost`; first cause
and exact cancellation timing remain unknown. Separate fresh stdio checks then
exposed all 40 tools and passed lease status/begin/renew/end. Automatic Wi-Fi
reassociation and repeated recovery remain unqualified. These power-service
checks add no application effects or native installation/cycle acceptance.

Explicit cross-build ownership adoption is queued future work. It must pin
the old Resident build, verified install receipt, immutable stage and hashes;
read-only validation must match all eight installed files. A distinct new
adoption receipt must preserve the prior records and bind their evidence to
the new build. Adoption is not implemented, and current permissions remain unchanged.
[Keep-awake evidence and remaining gates](RESIDENT-KEEP-AWAKE.md).

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
At that activation, native instance `9204e9d29165a6240627fd0b670e273c` was
unblocked and reported the installer ready, with Promoter unloaded. Twenty-two retained files
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

At this point, four cycles across two native builds had qualified install, launch, evaluation,
cooperative exit and redeploy for the dedicated owned Lab under this exact
Resident build.

### Same-build normal-reboot durability pass

The operator then confirmed a normal reboot without holding L, with the same
configuration and both FTP/file manager and Starter closed. GET-only checks
verified the same Resident build under fresh native instance
`abe54b2644227704aa00976a0ba4ad12`. It was ready and unblocked with Promoter
unloaded and no running apps. All eight retained install/launch receipts were
unchanged, each with `dispatch_count: 1`; all 24 stage-file hashes matched.
The proof performed zero device mutations and found no effect replay. The
original first-build unknown receipt remains retained and has not been retried.

The first combined readiness assertion was inconclusive because its initial
samples were not retained. A subsequent separately saved ready status and the
full captured durability proof passed. These are distinct observations; the
inconclusive assertion is preserved. The GET-only reboot proof itself added no
install/launch cycle; a subsequent fresh execution is recorded below.

A subsequent GET-only preview timed out before producing a plan or any device
mutation. Its error was retained; two later read-only status observations
reported ready under the same instance. A fresh preview was then used for one
new execution, which passed as the fifth cycle below.
These transport observations do not establish the timeout's cause.

This qualifies a normal reboot after completed work for the same exact build.
It does not qualify an interrupted native operation or power cut. Arbitrary
apps, DevLoop generalization, automatic Control bootstrap, broader devices,
long unattended operation and a complete autonomous platform session remain
unqualified.

### Redeployment after reboot

A fresh hash-bound execution after that reboot passed installation and launch
of the same Lab 01.01 variant 2 build
`b52ad43ee9846c5f1698b1a5dfb048959cb782638589a0e36234925091d170d6`.
Job `9ade8e32b2ee460aa1c00db718ebf21b` ran under native instance
`abe54b2644227704aa00976a0ba4ad12`, proving that persisted ownership accepted
redeployment after a normal reboot. Install/launch native, operation and cleanup
results were zero, with each operation dispatched once. Runtime PID `1057979`
and run `35c6a6506628e4121ec3a1220becf184` matched the exact candidate;
frames advanced from 190 to 255, and the deterministic self-test passed with
checksum `2727420034`. Cooperative exit and two independent absence observations
passed, leaving `native_lab_left_running: false`. The job took 53.576 seconds;
its separate read-only reconciliation passed with zero device mutations.

The qualified total is **five native cycles across two builds and four jobs**.
The single-cycle jobs observed 33.395–53.576 seconds; the two-cycle job took
90.317 seconds. These measurements describe this test connection and are not a
performance guarantee. Interrupted-native and power-cut recovery, arbitrary
titles, general DevLoop installation and automatic Control startup remain
unqualified.

### Registered MCP readiness pass

After the PC Resident MCP was restarted, its actual registered catalog exposed
all **36 tools**: seven Resident, thirteen Control and sixteen Workbench. Direct
registered calls passed exact Resident 0.1.5 status, an unexecuted native preview
under the same post-reboot instance for the exact variant 2 candidate, and
GET-only reconciliation of the completed post-reboot job. Reconciliation found
two retained receipts and a complete stage, with zero device mutations. These
read-only registered-client checks are separate from the five mutating cycles
run through fresh stdio sessions; the preview plan was not executed.

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
and launch with a different build. The exact same-build normal-reboot proof
and post-reboot redeployment passed above; interrupted operations, power cuts
and longer repeated cycles need separate evidence. Generalizing this adapter
to DevLoop or other project titles follows those lab results.
