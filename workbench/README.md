# Vita Workbench

Workbench supplies hash-pinned Lua trials, candidate staging, input qualification, screen evidence, metrics, managed-file recovery and paused restoration. It adds ten tools to the existing Resident MCP (27 tools total). Package installation remains manual.

Start with `vita_workbench_doctor`. Boot Resident can stage candidates even if runtime Control is absent after reboot. Screen/input work requires Control Starter's matched pair loaded once. Lua trials require foreground DevLoop 01.02 or the public 01.03 candidate paused; native input qualification requires Input Target (`CHRS00012`).

## Trial workflow

1. Edit a project under `workbench/projects`, update the source/profile SHA-256 hashes and pin the Control build from its build report. Smoke and input profiles provide examples.
2. Call `vita_workbench_run_trial` with relative profile, profile hash and Control build. Limits are 16 KiB source, 60 seconds, 20 steps and five seconds total input leases.
3. Inspect metrics, images, expiry and restoration. Requests are not replayed after uncertain replies. Changed ownership/revision prevents restoration over someone else's experiment.
4. Read `evidence/workbench/.../report.json` using `vita_workbench_read_report`. Mutation intent is journaled before requests. Power heartbeats have a separate journal.

Native physics, ball, added obstacles and score are preserved; the previous mode is restored paused. An originally unloaded VM can remain loaded but inactive after native restoration. Failed restoration fails the trial. A cross-process lock prevents competing bridges during a job.

`workbench/prove_device.py` runs separate `input`, `files`, `trials` and `soak` gates through a fresh stdio MCP, pinning current native build reports. A failed button mask remains a failure while the independent focus result is retained. Shoulder buttons are checked separately and in a combined mask. `watch_activity.py` supplies a bounded physical observation; its long window accommodates manual response time while each device work lease stays at 30 seconds. Creating `stop.requested` inside that observation's evidence directory ends it with cleanup.

Focus qualification polls read-only status while app exit completes, before any explicit release. A fresh kernel FOCUS cause and changed displayed PID are required; expiry and manual cleanup cannot count as focus proof. Physical observers keep their latest 128 samples in the readable report and all samples in `samples.jsonl`.

`watch_controls.py` observes five human gestures in paused native DevLoop: D-pad LEFT, each stick, front touch along the bottom edge and rear touch. Keep the Vita flat, wait for a separate dim cycle before each gesture, and hold it for eight seconds to accommodate network delays. This observer distinguishes sticks and panels through foreground telemetry, excludes motion or mixed input, and requires neutral release. It retains 64 recent samples plus the complete log; `--start-at` permits a fresh repeat from a particular gesture without erasing earlier evidence. Short gestures can fall between separate HTTP snapshots; a neutral sample at onset waits for a paired read instead of declaring a failure. Human visual confirmation remains separate.

`watch_disconnect.py sleep` or `wifi` renews bounded work until the first failed read, then stops heartbeats and only probes read-only recovery. A Wi-Fi pass requires reconnection before the last accepted lease expires, restored brightness, cleared work/dimming and unchanged inactivity progression. Leave the Vita still and disconnect its network externally for that independent gate. Changing Wi-Fi in Settings or carrying it out of range introduces physical activity. Manual sleep/wake uses the power button; the observer cannot force-wake it or reload native modules.

After an uncertain upload or copy, call `vita_workbench_verify_file` with its attempt, name, exact byte count, SHA-256 and Control build. The tool checks native hashes before and after two complete reads, retains `verified.bin` on the PC, and does not rewrite the device file. Its 30-second socket timeout accommodates bulk reads; verification failure is retained without replay. Keep the original mutation failure as separate evidence. `prove_synthetic_idle.py` checks that emulated controls leave idle dimming intact while work continues.

`vita_workbench_soak` checks status/capture for 10..3600 seconds with temporary work leases. It checks build, uptime, sequence and absence of synthetic input, and records latency. Wi-Fi and capture load affect device results.

## Power and native workflow

Screen/input/file/app work renews a temporary 30-second keep-awake lease. Workbench jobs renew while active and end it in cleanup. Default dimming starts after 30 seconds without device activity, including motion, and uses 20% of observed brightness. Input, end/expiry or Wi-Fi loss restores brightness. Saved settings remain untouched. Power status reports brightness and motion freshness; work lease supports an external bounded job. Status reads alone do not renew.

Build with `Build-Control.ps1` and `Build-Workbench.ps1`. `vita_workbench_stage_candidate` accepts the exact current Starter or Target package, checks source/package/accepted-artifact hashes, journals one boot-Resident upload and verifies two readbacks. It does not activate packages.

`vita_workbench_qualify_input` checks normal buttons, both additive sticks, both panels, neutral after expiry and kernel focus cancellation after Target self-exit. Pin both builds. Software input delivery is separate from physical controls, motion, brightness and sleep/wake acceptance.

The CLI is `.venv-devloop/Scripts/python.exe -m workbench.cli`; use `--help`. Restart the PC Resident MCP after bridge updates to expose all ten Workbench tools. Never restart Starter twice per boot or edit boot config for this candidate.

## Evidence boundary

Host checks exercise real code/MCP with simulated adapters. ARM/package checks establish exact identity; staging proves inbox bytes. Runtime and physical acceptance are separate. Development Control 0.3.3 passed all software input channels, separate shoulders, expiry and independent focus cancellation, power readbacks, synthetic-input idle filtering, both Lua trials with paused restoration, and managed-file verification/recovery. File confirmations and capture latency can vary with the connection; recovery does not erase an earlier failure. See [current qualification](../docs/QUALIFICATION.md) for capture timing and [release gates](../docs/RELEASE-CHECKLIST.md). Wi-Fi-loss restoration, manual sleep/wake and each individual physical input class remain separate gates. Unattended native installation, forced wake, unrestricted filesystem control and higher-rate video are not implemented.
