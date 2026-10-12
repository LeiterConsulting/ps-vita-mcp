# Autonomous DevLoop candidate

Development resumed on October 11, 2026 toward rapid app/game development with human involvement for physical testing and device recovery. This source candidate adds automatic runtime preparation and a separate deferred-startup experiment. It does not yet deliver unattended native installation, qualified persistent startup, or a complete autonomous development session.

The combined PC MCP catalog has **28 tools**: four Resident, thirteen Control and eleven Workbench. The foreground DevLoop bridge retains its separate ten tools. The [PC guide](PC-SIDE.md) covers configuration and registration; the [manual setup path](GETTING-STARTED.md) remains available.

## Runtime preparation and target identity

Call `vita_workbench_doctor` to inspect services, then `vita_workbench_prepare_devloop` with the exact installed Control build ID and selected DevLoop version. Preparation refuses an existing input/work lease, pins both endpoints including the effective Control port, and requires healthy paused DevLoop. It can submit `CHRS00003` launch once when the runtime is transport-unavailable. It journals the intent first and inspects an uncertain result without repeating the launch. Authentication, protocol, version and configuration failures do not authorize a launch.

Preparation observes advancing runtime frames, stable revision/source ownership, progressing captures and a stable captured PID. Readiness has two separate meanings:

| Report field | Meaning |
| --- | --- |
| `ready_for_script_reload` | Healthy paused Lua runtime is available for script-only work; captured foreground identity can remain unverified. |
| `ready_for_input_trial` | Native DevLoop 01.04 reports `title_id: CHRS00003` and a positive integer PID matching both captured foreground observations; its stable native build matches the caller's exact expected build pin. |
| `ready_for_lua_trial` | Compatibility field with the same strict input readiness requirement. |
| `result: runtime_ready_target_unverified` | Runtime inspection/script work is available; synthetic input is blocked. |
| `result: runtime_ready_build_unpinned` | The 01.04 target is mapped, but no expected native build pin was supplied. Script work is available; synthetic input is blocked. |

The 01.04 native source publishes `title_id`, `pid`, `run` and `build_id` in successful status, script, input and log responses. `run` is a per-process correlation value, not a credential; `build_id` fingerprints the declared native source and pinned build inputs. Preparation and trials retain the full runtime identity, stop after a process/build change, and refuse restoration into a different runtime. Input readiness/trials require `expected_devloop_build` to pin the reviewed candidate; the CLI spelling is `--devloop-build`. It is optional only for script-only 01.04 work. Read the pin from the actual build report's `nativeIdentity.buildId` or `package.buildId`. Reports distinguish `native_candidate_pin_verified` from `captured_target_mapped`.

Legacy 01.02 and 01.03 do not publish this mapping. A stable display PID alone could belong to LiveArea or another application. Consequently those legacy runtimes cannot run input-bearing Workbench profiles. Script-only profiles with no input steps remain available when explicitly selecting the legacy version. DevLoop 01.04 passed its pinned-SDK native build, installation, stable native identity and 55-step physical-device Lua reload/recovery proof, including original native scene restoration paused. Control capture-to-PID mapping, synthetic input and sleep/reopen remain open. [Candidate identities and evidence](autonomous-candidate-validation.json).

`vita_workbench_run_trial` rechecks native target identity before loading an input-bearing profile and before each synthetic step. Trials freeze their own endpoints, retain profile/source/Control pins, journal mutations and restore an owned scene paused. The PC lock prevents competing local jobs; it is not a general multi-host ownership protocol. Human input and physical sensor acceptance remain independent.

For the CLI, `prepare <Control-build-ID> --version 01.04 --devloop-build <DevLoop-build-ID> --timeout 30` succeeds only with input readiness. Version 01.04 is the default. Add `--script-only` to accept script readiness without target mapping; for an installed legacy runtime also select `--version 01.02` or `--version 01.03` and omit the unsupported native build pin. Polling uses the selected 2–60-second deadline plus in-flight socket timeouts. [Workbench details](../workbench/README.md).

## Experimental one-shot startup

The existing manual path loads Control Starter once after a confirmed normal boot. Do not add the Control kernel/service directly to tai boot configuration: that earlier arrangement hung. The new independent user plugin instead returns from `module_start` after starting its worker, then waits for delayed LiveArea readiness before attempting the matched pair.

The [native helper guide](../resident/autostart/README.md) describes its fixed file hashes, Shell metadata probe, cancellation marker and retained duplicate-load guards. It is disabled by default and consumes an explicit `enable.once` opt-in before native submission. It never retries a module load or deletes its guards. The final successful native state means **modules submitted; network unverified**; externally observed exact Resident/Control identities are a separate gate.

Build the experiment separately after building the matched Control artifacts:

```powershell
.\Build-Control.ps1
.\Build-Autostart.ps1
```

The build helper produces a unique fixed setup path, artifacts and `dist/autostart/build-report.json`. Running a build does not stage, activate or qualify them. Retain the actual report and rollback configuration. Stage with startup disabled, verify an ordinary boot, then arm one controlled trial only after inspection and confirmation of a clean boot with no prior pair loaded. Native installation, configuration activation, boot testing and recovery still require an operator.

On October 11, the helper's pinned-SDK native build passed, and seven files were staged with two hash readbacks each. That staging preserved the active configuration and pairing and created no active opt-in. After the operator activated the proposal and rebooted normally, the worker logged a disabled completion, expected Resident answered and Control was unavailable. The disabled-boot gate passed. A later explicit `enable.once` was armed with two readbacks. Its boot was normal and logs confirmed delayed readiness, exact hashes, consumed opt-in, matched Shell probe and service submission; Control then reported work-power worker failure and never exposed its network service. This is a failed service-startup trial, not complete startup acceptance. Retained guards block retry until recovery and inspection. A nested staged `enable.once` alone does not arm the helper. [Sanitized candidate record](autonomous-candidate-validation.json).

The one-shot experiment does **not** implement automatic startup across repeated boots. Do not remove markers to force another attempt while modules may be loaded. Persistent mode requires a separate design and qualification for duplicate detection, repeated normal boots, sleep/wake, Wi-Fi recovery and bounded failure behavior.

The separate [boot resource diagnostic](../resident/boot_diagnostic/README.md) investigates the masked mutex/thread failure through raw SDK returns after the delayed readiness gate. It loads no Control kernel, service or other plugin and exposes no network service. Success in this isolated probe would not establish Control startup or MCP readiness.

## Evidence and privacy

CI exercises actual C sources through simulated SDK adapters, preparation decisions, HTTP/MCP exchanges and staging faults. Host tests and native artifact checks are separate from physical boot, screen, input and application behavior. The [release checklist](RELEASE-CHECKLIST.md) records remaining gates; earlier [qualification](QUALIFICATION.md) stays bound to its historical package identities.

The iPhone app implementation remains private. Public protocol documentation and its [usage guide](IPHONE-COMPANION.md) are available; Swift/Xcode/signing/build/handoff artifacts are excluded. Keep tokens, raw device configuration, captures and detailed journals in ignored local directories.
