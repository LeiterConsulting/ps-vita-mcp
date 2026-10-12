# Resident managed inbox inspection

The corrected Resident **0.1.5** is currently boot-loaded and exact-binary verified, with a fresh unblocked, installer-ready native instance and Promoter unloaded. Five fixed-Lab install/launch/evaluate/graceful-exit cycles across two native builds passed on hardware; same-build journal durability passed after a normal reboot without replay; the earlier unknown receipt is retained without replay. [Current incident](NATIVE-LIFECYCLE.md#october-12-native-promotion-incident). The following historical Resident **0.1.4** results remain rollback evidence. It
passed a user-confirmed normal boot, initial read-only inbox inspection and a
separate DevLoop coexistence/upload check. The earlier October 12 fresh-stdio
and registered MCP checks exposed the 33 tools available at that point; direct registered-tool
calls passed exact 0.1.4 status, managed attempt listing, size/SHA-256 and a
complete 4096-byte read with independent full-file hash verification. Resident 0.1.3 and
0.1.2 rollback plugins and saved administrator pairing are preserved. The
existing upload and published-file verification tools remain compatible with
older supported versions; these three inspection tools were introduced in 0.1.4.

This is the first implemented slice of the [file-service roadmap](FILE-SERVICE-ROADMAP.md).
It inspects the existing inbox through Resident's background HTTP worker,
without Control, Starter or FTP. It adds no file writes, deletion, installation,
launching or configuration updates. The legacy launch broker stays disabled;
the separate 0.1.5 [native lifecycle candidate](NATIVE-LIFECYCLE.md) targets only
the owned Lifecycle Lab and still requires hardware qualification.

## Desktop tools

| Tool | Arguments and result |
| --- | --- |
| `vita_resident_list_inbox` | Optional `attempt` and `offset` (default 0). Lists inbox attempt directories or the permitted files in one attempt. |
| `vita_resident_file_info` | `attempt`, `file`. Returns observed byte size and SHA-256, including an empty or retained partial file. |
| `vita_resident_read_file` | `attempt`, `file`, exact `expected_sha256` and `expected_bytes`, optional `offset` (default 0), `length` (default 16384). Returns up to 16 KiB as base64, bracketed by matching size/hash observations. |

Attempt IDs must be 32 lowercase hexadecimal characters. File names are exactly
`package.vpk`, `probe.bin`, `package.vpk.part` or `probe.bin.part`. Inspection
accepts regular files from zero through 8 MiB; the existing probe **upload**
limit is still 64 KiB. The tools freeze the configured endpoint for each
operation. They reject unsupported service versions, malformed schemas,
unexpected names, mismatched size/hash pins and incomplete reads.

A retained `.part` hash describes the bytes observed. No persisted upload
manifest associates that file with an intended completed artifact. Inspection
does not publish, repair or validate it as a successful upload. Use
`vita_resident_verify_upload` for two complete readbacks of a published file
against known local bytes. Never replay an uncertain upload merely because a
partial file exists.

The read tool independently hashes returned bytes when the requested range
covers the entire file. A partial range is an observation bracketed by matching
file hashes, not independent proof that those bytes belong to an atomic version
of the file. External filesystem changes can race these requests. The API
reports `snapshot: false` and does not claim transactional reads.

## HTTP contract

All routes require the desktop administrator bearer token. Individual phone
credentials have no file access. Canonical GET requests have no body:

```text
/storage/list?offset=0
/storage/list/<attempt>?offset=0
/storage/stat/<attempt>/<file>
/storage/read/<attempt>/<file>?offset=0&length=16384
```

The parser requires query keys in that order and decimal numbers without leading
zeros (except `0`). It rejects traversal, URL encoding, extra fields, duplicate
keys, alternate roots and unsupported leaves. The read length is 1–16384;
offsets are at most 8 MiB. Offset equal to file size returns an empty binary
body; an offset beyond it returns HTTP 416.

List and stat responses identify `app: "Vita Resident"`, `protocol: 1`,
`storage_protocol: 1`, their `operation` and exact attempt/file identity. List
entries include `name` and `kind`, plus `bytes` for a file. Root listings expose
only correctly named attempt directories; attempt listings expose only the
four permitted regular files within the size limit.

Each page considers up to 32 raw directory entries after skipping the requested
offset, excluding `.` and `..`, with one additional lookahead for `has_more`.
Unsupported entries consume pagination positions but are filtered from the
result. Offset is bounded to 0–1000. Follow `next_offset` rather than counting
visible entries.
An empty page can still have more entries. At the pagination cap,
`has_more: true`, `limit_reached: true` and `next_offset: null` report truncation.
Directory order is unspecified and can change between calls. A traversal over
changing pages is not an authoritative complete tree.

Filesystem work has a 10-second cooperative deadline, checked between SDK I/O
calls. It cannot interrupt a blocked native filesystem call. Read chunks are
buffered and checked before sending a success header. Whole-file hashes and
chunks retain one opened regular-file descriptor and compare its size again
before closing. Failed reads, size changes, close failures and expired work
return errors; the worker then remains available for another request.

The POSIX test adapter uses descriptor-relative `openat` and `O_NOFOLLOW` to
reject symlinks at each managed component. The Vita SDK adapter checks path
component kinds and uses `sceIoGetstatByFd` after opening. The SDK lacks the same
descriptor-relative path-walk guarantees; host symlink tests do not establish
native resistance to concurrent path replacement. Arbitrary device paths,
pairing/configuration files, launch tombstones and installed apps are outside
this namespace.

## Qualification

The complete 23-group host suite and native ARM artifact checks passed. Separate hardware activation passed a user-confirmed normal boot and two exact plugin/configuration readbacks. Both rollback plugins, saved administrator pairing and withdrawn-experiment disable markers were preserved, with no configuration override. [Dated validation](managed-files-validation.json).

Twelve initial read-only checks passed, including fresh actual 33-tool stdio MCP and direct native HTTP checks: root and fixture-attempt listing; complete hashes and reads of a 4096-byte `probe.bin`, a 97-byte `probe.bin.part` and an empty `package.vpk.part`; a 113-byte middle range and empty EOF; and malformed-query, private-leaf, out-of-range and unauthenticated refusals. This proof made no mutation requests. The range check did not claim independent whole-file verification. Resident kept one disabled, unblocked broker instance with advancing time after inspection and refusals.

A separate coexistence check passed with DevLoop 01.04 open and paused. Eight samples retained exact DevLoop identity and revision while frames advanced, and Resident retained the same boot and native instance. A new 4096-byte upload passed two complete publication readbacks plus exact managed stat/hash and full-file readback. The broker remained disabled and unblocked. These checks made no Control, input, power or Lua changes.

Host coverage uses the actual C HTTP service under ASan/UBSan and actual stdio
MCP against simulated HTTP, including malformed requests, access denial,
pagination, retained files, symlinks, partial/failed reads, deadline recovery and
strict PC response validation. The native build report binds the exact source
fingerprint, imports and artifact hashes. Neither is hardware acceptance.

For future updates, preserve the installed configuration/plugin, both retained
rollback plugins, saved pairing and withdrawn-experiment disable markers. Stage
an immutable replacement and rollback, verify readbacks, then perform a separate
manual config copy and normal boot. Do not arm either boot experiment. Repeated
normal boot, storage durability across reboot, individual phone credential
confirmation, foreground/protected-UI launch policy, managed asset writes,
resumable chunks, quotas, native installation and automatic app launching remain
separate gates. The passed foreground coexistence test does not attest which
application the native launch policy can safely replace.
