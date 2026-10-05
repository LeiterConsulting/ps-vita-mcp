# Workbench qualification on October 4 2026

PS Vita MCP now includes ten Workbench tools for hash-pinned trials, input qualification, capture checks, power leases, candidate staging and recovery of uncertain file transfers. The development Control 0.3.3 build passed the unattended software gates below on one firmware 3.65 Vita. **Physical touch restoration and lifecycle acceptance remain open.** The public checkout builds separate packages; these need their own installation and device qualification before a binary release.

The [machine-readable qualification record](workbench-qualification.json) binds results to development package identities and hashes of retained private reports. The [public build record](workbench-public-build-validation.json) identifies the separate publication artifacts. Raw device journals, pairing, local paths and generated binaries are excluded from source publication.

## Development device results

| Gate | Result | Scope |
| --- | --- | --- |
| Activation and identity | Passed | Starter 01.04 loaded the matched Control 0.3.3 pair once after normal reboot. Registered desktop MCP reported the expected ABI 2 fingerprint. |
| Idle dimming and restoration | Passed device readbacks | Fresh motion, idle dimming, explicit end and independent lease expiry were observed. This does not establish visible restoration from physical touch. |
| Synthetic input exclusion | Passed | L, R, combined sticks and both emulated panels were delivered while dimming stayed intact and inactivity continued. Expiry returned input to neutral. |
| Input Target qualification | Passed | Normal button masks, separate L/R, both sticks, both panels and expiry were observed by app telemetry. Target self-exit produced fresh kernel focus cancellation before any cleanup release. |
| Lua trials | Passed | Smoke and five-channel input profiles met metrics through actual stdio MCP. The original native scene, physics, ball, score and obstacles were restored paused. |
| Managed file recovery | Passed recovery; original confirmation uncertain | A 1 MiB publication had an uncertain confirmation and was not replayed. Native hash and two complete reads proved its bytes. Copy, two reads, hash-guarded deletion of the owned copy and preservation of the original passed. |
| Capture soak | Completion unconfirmed | The requested 600-second run retained 356 progressing captures over about 556 seconds. Its report remains pending and has no final cleanup receipt. It is not a passed soak. |

Control remained reachable in a later read-only check, with both input and work leases at zero. DevLoop and Input Target were unavailable then. No forced wake or foreground launch was attempted during that check. The reason the long run stopped is not established.

### Capture timing

The incomplete run used the RLE preview path and retained a stable Control fingerprint and displayed process across its 356 saved samples. Median screen round trip was **88.49 ms**, with a maximum of **2,738.24 ms**. These are network-and-capture observations from one interrupted run, not sustained video, end-to-end interaction latency or a performance guarantee. A completed bounded soak and longer lifecycle trials are still required.

### App transition and transfer limits

An accepted native launch command initially left a LiveArea confirmation asking to close DevLoop. A screen-guided bounded front-panel tap dismissed that observed dialog, after which Input Target telemetry proved launch. Simulated button presses did not dismiss it. This establishes that specific transition only; generic system UI automation and unattended native installation remain outside the qualified capability.

Managed files are confined to the Control workspace. Lost publication or copy replies can describe completed writes. Preserve the exact attempt, name, byte count and SHA-256; use `vita_workbench_verify_file` for native hashes and two reads before another mutation. Recovery establishes file contents without erasing the original failure. The protocol permits up to 8 MiB, but this pass qualifies a 1 MiB fixture only.

## Physical touch repair

The earlier touch observer stayed dim despite physical front-panel contact. Inspection found two defects in freshness handling: foreground and Shell polling were conflated, and touch source timestamps were compared with a different kernel clock. Control 0.3.3 separates readers and uses source advancement plus kernel receipt time. Its host harness exercises independent clocks, foreground isolation, held contacts, release, duplicate expiry, eviction and synthetic exclusion.

Live zero-contact samples now advance under the foreground reader despite the different clock epochs. Synthetic delivery and idle filtering also passed. **Neither observation proves that physical contact brightens the display.** Front and rear held-contact tests, visible confirmation, and button/stick/motion regressions on this exact build remain required. Older physical button, stick and motion successes are useful history, not acceptance of the repaired package.

## Public source and package checks

The publication checkout imports only the allowlisted Control and Workbench files in [the source manifest](workbench-source-import.json). It retains configurable staging and guard retirement, disables legacy Control boot activation, includes original-code licenses in Starter and Target, and accepts DevLoop 01.02 or 01.03 in both trial and readiness checks.

The combined background server exposes **27 tools**: four Resident, thirteen Control and ten Workbench. Foreground and background bridges share a process lock. Hash and revision checks refuse drift, journals precede mutations, uncertain device operations are not replayed, and cleanup restores the owned scene paused.

The Windows aggregate build checks native C under host adapters, actual stdio MCP against local fixtures, FTP faults, ARM modules, SELF attributes and package identities. The GitHub host workflow runs portable host contracts without contacting a Vita; it does not build or certify installable release packages. Public Starter has eleven package entries and Target has seven, including the project license; the development packages had ten and six. Public fingerprints and package hashes therefore have their own acceptance record.

## Release decision

The source is suitable for review as a developer preview candidate. A final binary release is blocked on the [release checklist](RELEASE-CHECKLIST.md): physical restoration, completed capture and lifecycle trials, exact public-package device acceptance, complete linked-library notices and independent setup reproduction. Autonomous Lua trials and bounded input are implemented; forced wake, arbitrary device file access, automatic VPK installation and continuous video are not implemented.
