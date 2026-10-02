# Architecture

## The first implementation

Vita DevLoop has two cooperating components:

| Component | Responsibility |
| --- | --- |
| Desktop MCP bridge | Expose tools and resources, authenticate device requests, return images/structured results, and perform verified package staging |
| Native Vita host | Read hardware, run the native or Lua experiment, draw the scene, apply queued changes, publish snapshots and capture its framebuffer |

The desktop bridge currently uses Python and MCP over stdio. The Vita host uses C, libvita2d and Lua 5.4. The native build uses a digest-pinned VitaSDK container. The public source import will retain those build inputs and dependency notices.

## Commands and observations

Mutations carry an expected revision. The app applies them on the main thread between simulation frames and publishes the resulting snapshot before acknowledging completion. Local interactions can also change that revision.

A stale revision is rejected. A timed-out change is not silently replayed: the client reads status to establish what happened before choosing another action. Frame/revision metadata ties an observation to the app state it captured.

## Lua replacement and recovery

A candidate script is compiled in a fresh VM and preflighted before becoming active. A rejected candidate leaves the current script intact. A successful candidate starts paused, and one previous VM can be retained for rollback.

Runtime callback failures pause the experiment and report the error while keeping inspection available. Restart reconstructs the current script; rollback selects the retained prior VM; native fallback returns to the built-in experiment.

The prototype limits source, allocations, instructions and drawing commands. These limits provide development containment, not a security boundary for hostile code.

## Capture and input

Screenshots capture DevLoop's own framebuffer, with copying coordinated on the main thread and PNG encoding handled by the network worker. This is an on-demand still image, not system-wide video capture.

Input observations include read status alongside values so an unavailable sensor can be distinguished from a zero reading. The current tool surface does not inject physical controls.

## Packaging and installation

Native app updates use a separate path: build and validate the selected package, upload to a fresh FTP inbox as a temporary file, read it back and verify its hash, rename it, then verify the final file again. The user installs it through the Vita file manager.

The existing uploader accepts the DevLoop identity. General project/package support will need an explicit registry and its own validation.

## Reuse beyond DevLoop

A later native integration layer could expose app-specific observations and commands inside other homebrew projects. Each app would define its supported operations, lifecycle and state model. The existing protocol and client behavior provide a starting point; a reusable integration library has not been released or validated yet.
