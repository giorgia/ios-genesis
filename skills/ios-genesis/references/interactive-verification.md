# Interactive Flow Verification

Lets `ios-visual-verifier` drive the app in the simulator (tap/type/read-UI) to verify per-screen *flows* via XcodeBuildMCP. Additive and optional — gated on XcodeBuildMCP being connected; graceful degrade to today's structural-only verification when it isn't. Applies to `ui_impact: true` tasks, the same projection as the existing visual_verification phase.

## Detection (orchestrator, at visual_verification phase start)

Check the session tool list for the XcodeBuildMCP automation tools — a tool whose name ends in `__describe_ui` and one ending in `__tap` (the registration prefix is set by the user's MCP config and is matched as a substring, exactly as `design-mode.md` matches the Figma prefix `mcp__claude_ai_Figma__*`). If present, pass `interactive: true` into every verifier dispatch this phase; else `interactive: false`. Subagents inherit the session's MCP tools, so the verifier can call them whenever the orchestrator detects them.

## Flow declaration (`design.md`, authored by the UI Designer)

Each screen carries a `### Flows to verify` list. Each item is a one-line natural-language goal (setup + action + expected outcome) plus a trailing tag: `sim` (default — drivable in the simulator) or `device` (needs real hardware unavailable in the Simulator, e.g. motion sensors). Self-seeding is expressed as setup steps inside a flow ("add three habits, then open Stats").

## Driving a flow (verifier, `interactive: true`)

For each `sim`-tagged flow of the screen, on the same UDID the structural check used: read the live UI (`describe_ui`), decide the next `tap` / `type_text` / `swipe` toward the goal, execute it, `screenshot` each step to `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/step-N.png` (solo dispatches, which have no `task_id`, use `.ios-orchestrator/screenshots/flow-<slug>/step-N.png`), then assert the expected outcome by reading the final screen. A **step budget of <=12 actions per flow** bounds a confused run so it reports instead of thrashing.

## Verdicts

Per flow: `pass` | `issues_found` | `deferred_to_device` (tagged `device`, never driven in-sim) | `unverified_no_mcp` (`interactive: false`). Top-level `status` rollup: any `issues_found` -> `issues_found`; else any `deferred_to_device` -> `deferred_to_device`; else `pass`. `unverified_no_mcp` never changes the top-level status. `deferred_to_device` and `unverified_no_mcp` flows are recorded as `open_risks`.

## Device checkpoint (orchestrator)

When a task's `status` is `deferred_to_device`, the `visual_verification` checkpoint presents a real-device hand-off via `AskUserQuestion`: "These flows need a real device: [list]. Run them and report, or defer?" Report a result -> resolve the risk (pass) or route an `address_visual` fix / carry a risk (fail). Defer -> the flow stays an `open_risk` (pending device). Non-blocking — never a hard stop.

## Degrade (`interactive: false`)

The verifier runs the structural check only; every declared flow is `unverified_no_mcp` and recorded as an `open_risk`; the checkpoint notes "connect XcodeBuildMCP for interactive verification." The run is never failed over a missing MCP.

## Error handling (soft-fail)

Flow verdicts are exactly the four values above; infra failures are handled at task level. Flow blocked by the app (control missing, crash mid-flow) -> `issues_found` + failing step screenshot. Simulator dies mid-flow -> whole task `status: skipped`, no flow verdicts. Verifier stuck past the step budget -> `issues_found` (app defect) or an `open_risk` (ambiguous flow spec). Router miss -> verify root only + risk; that screen's flows each become an `open_risk` ("flow unverified: screen `<name>` unreachable"), never false findings.
