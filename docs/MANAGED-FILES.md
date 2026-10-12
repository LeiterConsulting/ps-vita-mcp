# Resident managed inbox inspection

As of October 12, 2026, the source adds Resident **0.1.4** and three desktop
inspection tools. The test Vita still runs **0.1.3**. Building or passing host
tests does not activate this candidate or qualify its native filesystem APIs.
The existing upload and published-file verification tools remain compatible
with older supported Resident versions. These three tools require 0.1.4.

This is the first implemented slice of the [file-service roadmap](FILE-SERVICE-ROADMAP.md).
It inspects the existing inbox through Resident's background HTTP worker,
without Control, Starter or FTP. It adds no file writes, deletion, installation,
launching or configuration updates. Native launch submission stays disabled.

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

Pages scan at most 32 raw directory entries, excluding `.` and `..`; unsupported
entries consume pagination positions but are filtered from the result. Offset
is bounded to 0–1000. Follow `next_offset` rather than counting visible entries.
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

The complete 23-group host suite and native ARM artifact checks passed. The replacement and isolated known-byte fixtures are staged with two readbacks per file, with active configuration unchanged and both rollback plugins retained. A fresh 33-tool MCP process passed exact installed 0.1.3 status and explicitly refused its unsupported inspection tools. [Dated validation](managed-files-validation.json).

Host coverage uses the actual C HTTP service under ASan/UBSan and actual stdio
MCP against simulated HTTP, including malformed requests, access denial,
pagination, retained files, symlinks, partial/failed reads, deadline recovery and
strict PC response validation. The native build report binds the exact source
fingerprint, imports and artifact hashes. Neither is hardware acceptance.

Before activation, preserve the installed 0.1.3 configuration/plugin, its 0.1.2
rollback, saved pairing and both withdrawn-experiment disable markers. Stage
the immutable replacement and rollback, verify readbacks, then perform a
separate manual config copy and normal boot. Do not arm either boot experiment.
On hardware, compare listings, sizes, full hashes and binary ranges with known
PC files; inspect a retained partial without changing it; recheck status,
pairing and the disabled broker with DevLoop open. Storage durability across
reboot, managed asset writes, resumable chunks, quotas, native installation and
automatic app launching remain separate future gates.
