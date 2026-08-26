# Interactive Flow Verification

Lets `ios-visual-verifier` drive the app in the simulator (tap/type/read-UI) to verify per-screen *flows* via XcodeBuildMCP. Additive and optional — gated on XcodeBuildMCP being connected; graceful degrade to today's structural-only verification when it isn't. Applies to `ui_impact: true` tasks, the same projection as the existing visual_verification phase.

## Detection (orchestrator, at visual_verification phase start)

Detection happens **once per run, at the capability preflight** (`references/capability-preflight.md`), not at this phase. Read its `ui_read` and `ui_act` results: `interactive: true` requires both, and the verifier dispatch carries `ui_read_tool` set to the full tool name the preflight actually matched (`snapshot_ui`, or `describe_ui` on older XcodeBuildMCP releases), so the verifier calls a name that exists. Subagents inherit the session's MCP tools, so a detected tool is callable — *provided* the verifier's `tools:` grant covers the server's registered name, which is the `⚠` case the preflight reports.

Both halves must be present: XcodeBuildMCP ships UI automation as a separate `ui-automation` workflow that is **off by default**, so a session can expose the simulator tools (`build_run_sim`, `screenshot`, …) and even `snapshot_ui` while `tap`/`type_text`/`swipe` are absent. That is the common cause of `interactive: false`, and the fix the preflight prints is: add `"env": {"XCODEBUILDMCP_ENABLED_WORKFLOWS": "session-management,simulator,ui-automation"}` to the XcodeBuildMCP entry in the MCP config, then restart the session.

## Flow declaration (`design.md`, authored by the UI Designer)

Each screen carries a `### Flows to verify` list. Each item is a one-line natural-language goal (setup + action + expected outcome) plus a trailing tag: `sim` (default — drivable in the simulator) or `device` (needs real hardware unavailable in the Simulator, e.g. motion sensors). Self-seeding is expressed as setup steps inside a flow ("add three habits, then open Stats").

## Driving a flow (verifier, `interactive: true`)

For each `sim`-tagged flow of the screen, on the same UDID the structural check used: read the live UI (the dispatch's `ui_read_tool` — `snapshot_ui`, or `describe_ui` on older XcodeBuildMCP), decide the next `tap` / `type_text` / `swipe` toward the goal, execute it, `screenshot` each step to `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/step-N.png` (solo dispatches, which have no `task_id`, use `.ios-orchestrator/screenshots/flow-<slug>/step-N.png`), then assert the expected outcome by reading the final screen. A **step budget of <=12 actions per flow** bounds a confused run so it reports instead of thrashing.

## Verdicts

Per flow: `pass` | `issues_found` | `deferred_to_device` (tagged `device`, never driven in-sim) | `unverified_no_mcp` (`interactive: false`). Top-level `status` rollup: any `issues_found` -> `issues_found`; else any `deferred_to_device` -> `deferred_to_device`; else `pass`. `unverified_no_mcp` never changes the top-level status. `deferred_to_device` and `unverified_no_mcp` flows are recorded as `open_risks`.

## Device checkpoint (orchestrator)

When a task's `status` is `deferred_to_device`, the `visual_verification` checkpoint presents a real-device hand-off via `AskUserQuestion`: "These flows need a real device: [list]. Run them and report, or defer?" Report a result -> resolve the risk (pass) or route an `address_visual` fix / carry a risk (fail). Defer -> the flow stays an `open_risk` (pending device). Non-blocking — never a hard stop.

## Degrade (`interactive: false`)

The verifier runs the structural check only; every declared flow is `unverified_no_mcp` and recorded as an `open_risk`; the checkpoint notes the `XCODEBUILDMCP_ENABLED_WORKFLOWS` fix above. The run is never failed over a missing MCP.

**Degrading means reporting, not substituting.** The verifier holds `Bash`, and the underlying simulator-automation CLI (AXe — `describe-ui`/`tap`/`type`, which is what XcodeBuildMCP's UI-automation tools wrap, bundled inside the package) is reachable from a shell. Do not go get it: never `brew install`, `npm install`, `npx`, download, or invoke an automation binary to drive the simulator, and never substitute another automation path for the missing MCP tools. Installing software on the user's machine is not in the verifier's remit, and a pipeline that silently swaps its verification substrate reports results the user cannot reason about. Missing tools produce `unverified_no_mcp` and a one-line fix in the checkpoint — that is the whole of the fallback.

## Error handling (soft-fail)

Flow verdicts are exactly the four values above; infra failures are handled at task level. Flow blocked by the app (control missing, crash mid-flow) -> `issues_found` + failing step screenshot. Simulator dies mid-flow -> whole task `status: skipped`, no flow verdicts. Verifier stuck past the step budget -> `issues_found` (app defect) or an `open_risk` (ambiguous flow spec). Router miss -> verify root only + risk; that screen's flows each become an `open_risk` ("flow unverified: screen `<name>` unreachable"), never false findings.
