---
name: make-vita-app
description: Plan, build, or port PS Vita homebrew apps and games, then validate and iterate through PS Vita MCP. Use for make_vita_app requests, Vita prototypes, and source-port feasibility. Supports live Lua scenes and a single owned native development slot; standalone title deployment has a separate qualification boundary.
---

# Make Vita App

Turn the user's app or game idea into a testable Vita project. Preserve the requested deliverable: a plan stays a plan; making or porting includes implementation and validation within available capabilities. The natural spelling `make_vita_app` refers to this skill; its discoverable Codex name is `$make-vita-app`.

## Locate and choose a route

Resolve the PS Vita MCP checkout from the working directory, `VITA_APP_REPO`, or this installed skill's local `repository.json`. From the checkout run `tools/vita_app.py --help`; from elsewhere run the installed skill's own `scripts/vita_app.py --help` using its full path. Read the checkout's current `README.md` and applicable instructions; installed skill copies do not establish device qualification.

| Route | Use it for | Result |
| --- | --- | --- |
| Plan / port assessment | A plan request, unknown upstream constraints, or feasibility | A concrete proposal and smallest measurable experiment; zero device writes |
| Lua | Small 2D interfaces, simulations, games and input experiments using primitives and metrics | A scene inside installed DevLoop |
| Native development slot | Compiled prototypes or native APIs beyond the Lua sandbox | A source-built prototype in owned `VMCP00001`; one candidate occupies the bubble at a time |
| Standalone native port | A distinct title, larger asset layout or existing engine integration | Source/build work and a qualification plan until its own installer/runtime adapter is supported |

Do not silently reduce a standalone product to a scene. Explain the proposed first slice, continue independent useful work, and clarify only a consequential unresolved choice. Read [ports.md](references/ports.md) for ports, [lua.md](references/lua.md) for Lua, or [native.md](references/native.md) for native work.

## Create, evaluate, iterate

For plan-only work, finish the assessment described in `references/ports.md` without scaffolding app code, building or contacting the device. The sequence below applies to implementation requests.

1. Record intended behavior, delivery form, controls/resources, measurable acceptance checks and remaining physical checks. Use `tools/vita_app.py new` without replacing existing work; default projects and generated evidence are private and ignored.
2. Implement the requested behavior. Replace example tests with app-specific checks. Plan realistic budgets; a generic health check is not a gameplay test.
3. Run the real shared Lua host validator or native module's host assertions and pinned SDK build. Fix routine failures and repeat affected checks. Host execution, ARM/package validation, installation, live telemetry and physical/visual acceptance are distinct results.
4. Read current device status and exact identities before live work. Prefer registered MCP tools. Keep effects within the requested development scope; do not edit boot configuration or activate withdrawn startup experiments.
5. Execute bounded candidates with fresh pins, evaluate behavior, then improve and redeploy. Preserve sources, hashes, receipts and useful failure evidence. Report the runnable artifact, checks passed and remaining human testing.

## Lifecycle constraints

- Native prototypes use the existing owned slot and authenticated cooperative-exit envelope. Never relabel an unrelated VPK, bypass title allowlists, replace accepted DevLoop/Resident/Control or imply arbitrary-title installation.
- A timed-out effect is not permission to repeat it. Retain its job/attempt, reconcile read-only and stop dependent effects if outcome/ownership is unknown. Changed code/package needs a fresh preview.
- Native execution requires the conservative idle-shell guard; it does not prove every protected UI or displayed foreground. Preserve boot/sleep settings and unrelated files.
- Lua sessions require already-open healthy paused DevLoop 01.04. Control-free sessions do not open it, synthesize input, keep it awake or capture screens. Native slot cycles need only boot Resident when its live guard is ready.
- Keep credentials, raw journals/captures and private project material out of public source. iPhone source, signing and build artifacts remain private; public protocol guides are permitted.

Conclude with the outcome and evidence, explicitly naming the delivery form: plan, DevLoop scene, native development-slot prototype, or standalone package.
