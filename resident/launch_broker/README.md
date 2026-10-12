# Portable fixed-title launch broker

Resident **0.1.3 is an installed, disabled native qualification candidate**,
with 0.1.2 retained for rollback. The core, strict HTTP codec, immutable store,
native instance identity and read-only app inventory are linked into its native
module. Native submission is unconditionally refused; there is no enable file
or API. The operator confirmed normal boot; read-only checks matched the exact
plugin and proposed configuration and preserved administrator pairing and both
experiment disable markers. Control and DevLoop were unchanged, and neither
withdrawn boot experiment was activated.

The intended later operation is one authenticated PC request to open
`CHRS00003` (Vita DevLoop) after Resident is already healthy. The existing Resident
worker now has a dispatch boundary after response completion and successful
socket closure. The qualification candidate keeps it disabled and its native
callback refuses even an accidental dispatch. The core has no SDK imports, native module loaders, arbitrary
URI/path/title inputs, installation, input injection or boot-time dispatch.
The retained Resident 0.1.2 rollback has no broker namespace or random native instance identity
and must be refused by clients that require this contract.

Read the [native candidate and hardware gates](../../docs/RESIDENT-LAUNCH-CANDIDATE.md)
before any deployment. Tests cover actual Resident HTTP and real POSIX storage,
with a separately compiled simulated launch adapter. These are host checks,
not native filesystem durability, foreground or boot acceptance.

Initial hardware checks separately passed: three exact-build broker samples
retained one native instance with advancing time and `enabled`,
`configured_enabled` and `blocked` all false. Inventory resolved the running file
manager to an AppId/PID/title, with foreground/protected-UI/submission flags false.
Fresh stdio MCP status and a 4 KiB probe with two complete readbacks passed. The
same checks passed with DevLoop open, retaining Resident's start time. Eight
read-only observations matched inventory's `CHRS00003` PID to the stable exact
paused DevLoop build/PID/run and revision while frames advanced; Resident retained
its instance and advanced its clock. These samples changed no scene and do not
attest displayed foreground or protected UI.

A subsequent bounded Lua regression accepted both rate-60/rate-120 candidates,
selected the faster and restored the original native world paused under the
same DevLoop build/PID/run. Lua finished inactive with the last VM retained;
the broker kept its instance and stayed disabled and unblocked. Fresh stdio
verified the 30-tool catalog, both script tools and 0.1.3 status. The registered
desktop connection remains an older 28-tool process that rejects 0.1.3 and needs
a PC refresh. Storage durability across reboot, phone credential confirmation
and safe native launching remain open.

## Native qualification integration

`service.c` combines the core, `http.c`, `store.c` and `native_vita.c` in the
existing delayed Resident worker. No additional worker, boot entry, module load,
power policy or launch on initialization is added. One 16-byte SDK RNG call creates
the retained native instance ID; failure disables the broker while ordinary
Resident inspection stays available. Status clock samples also detect regression.

`GET /devloop-launch/status`, `GET /devloop-launch/inventory`, receipt GETs and
the reserved offer POST require the desktop administrator token. Phone credentials
cannot access this namespace. POST uses exactly seven bounded fields with no
duplicates, unknowns, escapes, NULs or numeric coercion. Native offers are denied
because the candidate is disabled. There is no client-supplied observation route.

The fixed `ux0:data/vita-resident/launch-v1` store has 128 immutable record slots.
An exclusive CLAIM record is the permanent attempt tombstone; later records chain
explicit little-endian fields and SHA-256 checksums. Each append requires complete
write, file/device sync and exact readback. Recovery rejects gaps, known orphan
suffixes, torn/noncanonical records, altered history and invalid transitions.
Capacity exhaustion blocks further writes; nothing is pruned. Without directory
enumeration, arbitrary unrelated filenames cannot be excluded. Only format 1 and
the exact compiled Resident build are supported: an older store is retained and
blocks this broker until an explicit migration policy exists. These qualification
bounds are not a long-term production retention policy.

App inventory maps App IDs to PIDs, then titles. Its separate reads are not atomic
and its bounded list is not foreground evidence. The pinned SDK does not establish
displayed foreground/protected-UI semantics through those calls. Accordingly
`foreground_verified`, `protected_ui_verified` and `native_submission_enabled`
remain false, and no AppMgr launch API is imported into this candidate.

## Core and adapter contract

`launch_broker.h` defines `lb_init`, `lb_offer`,
`lb_dispatch_after_response`, `lb_get`, `lb_observe` and `lb_set_enabled`.
All operations and adapter callbacks are **serialized and non-reentrant**. Any
future threaded HTTP host must serialize access to the whole core. An enabled native
launch callback may block the single service worker; the core cannot promise
continued HTTP responsiveness or bound/cancel that native call.

The trusted adapter supplies the actual Resident build ID and an immutable random
128-bit native instance ID at initialization. Generate this ID from an appropriate
native random source once per module instance; do not derive it from timestamps,
PID, a PC-supplied request, or a saved prior instance. The core can validate the
32-hex encoding, not the random source. `LBAuth.role` comes from the authenticated
transport's administrator-token check, never from a JSON body. Phone credentials
cannot offer, dispatch through an offer, inspect private receipts, or attest an
observation.

An offer pins the exact Resident build and current native instance, a fresh
32-hex attempt ID, literal `CHRS00003`, and the expected 64-hex DevLoop build. Its
`issued_ms` is from the broker's native monotonic clock. At acceptance it may be
at most 5,000 ms old; TTL is 1..10,000 ms, with checked overflow and expiry. A
clock regression blocks further offers/dispatch and invalidates cached readiness.
Clients freeze host/port/credentials and both identity pins for the entire job.

Storage callbacks have explicit return contracts in the header:

- `claim` exclusively creates a persistent attempt tombstone **and** the queued
  receipt, commits/syncs them, and enforces one active queued/dispatching attempt.
  Old tombstones survive restart and are never removed or reused. A known
  duplicate returns 1. Every other nonzero result is uncertain storage failure.
- `save` atomically commits/syncs the exact existing attempt and its current
  receipt. It cannot silently create a replacement attempt or drop its tombstone.
- `recover_last` and `lookup` validate bounded, versioned records before returning
  them. Persistent wire serialization is an adapter responsibility; do not dump
  the C struct with padding as a portable storage format.

Initialization never dispatches. Every recovered attempt, even an apparently
successful one or one with the same supplied instance, becomes `unknown/restart`
with no current runtime readiness. Storage uncertainty blocks the current core.
Cached uncertain receipts remain available to an authorized GET. A future new
instance cannot accept the previous instance's request pins. The PC journal must
never reuse an attempt or automatically replay after storage/transport failure;
no system can prove that a failed persistent claim left an intact tombstone.

## Boundaries and receipts

`lb_offer` first validates authorization, identity, time and title. It returns
`LB_ACCEPTED` (202) only after the adapter confirms a durable exclusive queue
record. This does not call the launch adapter. Duplicate or conflicting active
offers reject without adopting a new revision or launching.

After the socket closes, the trusted service hook calls
`lb_dispatch_after_response(attempt, response_complete)`. `response_complete`
means the server sent its response bytes; it does not prove the PC received them.
An incomplete response becomes unknown with zero native calls. A queued expiry or
disable becomes a terminal outcome before submission. The core durably stores
`dispatch_intent` before calling the adapter once, then rechecks expiry because
storage sync can take time. `dispatch_count` is this durable fence count, not
proof that AppMgr ran or that a game appeared.

A positive confirmed native return records `submitted`; a negative confirmed
return records `native_rejected`; a missing/invalid outcome records `unknown`.
Failure to store the final receipt also becomes unknown. None of these paths
retries, clears the fence, restarts a worker or launches during recovery. Expiry
during a blocking native call does **not** become a cancellation or rollback claim.
Use `lb_get` to reconcile the exact attempt instead of repeating POST.

GET can also retrieve an archived receipt without changing its original state or
pins. An old `observed_script_only` receipt describes historical observations;
authentication against the current broker does not turn it into current
readiness. Consumers must compare the receipt's Resident build, native instance
and exact attempt with their current job pins, then obtain fresh runtime
observations. Recovery invalidates the last attempt's readiness; it does not
rewrite every archived receipt.

Native submission cannot validate the installed DevLoop source build. A later
observer must separately inspect actual DevLoop 01.04 telemetry. `lb_observe`
requires the expected build, literal title/version, positive native PID, 32-hex
run identity, healthy paused state, and two observations with the same PID/run and
revision and advancing frames. A changed identity/ownership/health invalidates
readiness. `observed_script_only` establishes only these correlated telemetry
checks. It is not synthetic-input acceptance, display focus/capture mapping,
installation proof or proof that launch caused the observed process. The adapter
must obtain observations from the frozen actual foreground endpoint rather than
accepting untrusted client assertions as physical evidence.

Disable can prevent a still-queued submission. It cannot interrupt an already
executing native call. An unknown outcome blocks every new attempt in that native
instance, including reconstruction with the same instance ID. A genuinely new
native instance may accept a new, explicitly authorized job after recovery while
preserving every old attempt tombstone. Other terminal outcomes may permit a new
explicit job. Automatic retries with new attempt IDs are forbidden. Stable
Resident replies alone do not prove that displacing the current
foreground application is safe. An eventual launch requires an explicit dev-job
intent and the separately qualified foreground policy.

## Offline checks

```sh
sh resident/launch_broker/test_host.sh
sh resident/launch_broker/test_http.sh
sh resident/launch_broker/test_store.sh
sh resident/launch_broker/test_native_host.sh
sh resident/test_host.sh
```

The script builds `core.c` with strict C11 warnings, AddressSanitizer and
UndefinedBehaviorSanitizer, then runs the real C fixture. It injects durable
claim/save failures before and after commits, response loss, expiry during sync,
blocking native duration, negative/unconfirmed native results, restart across
queue/dispatch/outcome boundaries, persistent duplicate attempts, role/pin/title
rejections, disabled states and observed-runtime drift. No native call occurs on
initialization. Host fixtures do not model actual taiHEN loader scheduling,
AppMgr behavior, native random generation or real storage durability.
