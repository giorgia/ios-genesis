# ios-genesis v0.5.0 — Interactive-Flow Verification

## Problem

The visual verifier can only launch the app and screenshot the target screen — `simctl` has no tap support (the README's #1 known limitation). So anything behind interaction — onboarding, permission gates, filled-in forms, sheets, populated states — goes unverified. This is the through-line of both Cadenza dogfood findings: **Finding A** (nobody verifies the first-run *experience*) and **Finding B** (the pipeline can't self-verify interactive states, and cannot test hardware at all).

This feature lets `ios-visual-verifier` **drive the app in the simulator via XcodeBuildMCP** (tap/type/swipe/read-UI) to verify per-screen *flows*, while keeping the hardware-sensor gap honest via a distinct verdict and a real-device human checkpoint. It is additive and optional: gated on XcodeBuildMCP being connected, with graceful degrade to today's static verification when it isn't.

## Decisions made during brainstorming

- **Scope: interactive-flow verification only.** Not a UX-completeness *reasoning* agent (Finding A's deeper half), not the task-graph flow declaration, not an XCUITest fallback — those are deferred (§8).
- **Flow style: natural-language goals the verifier interprets.** A flow is a short NL goal ("set a goal to 50, confirm the counter shows 50"); the verifier reads the live UI via XcodeBuildMCP, decides the taps/types itself, and asserts the expected outcome. No brittle coordinate scripts authored in advance. Non-deterministic between runs — the assertion, not the path, is what's judged.
- **Flows authored by the UI Designer, in `design.md`.** Each screen gets a `### Flows to verify` list; the verifier reads them from the `design_summary` it already receives. The Architect's hardware risks inform which flows are tagged `device`.
- **Hardware honesty (Finding B).** Flows that need real hardware are tagged `device` and never driven in-sim; they get a distinct `deferred_to_device` verdict plus a real-device human checkpoint. A run is never a silent clean pass when a hardware-gated flow exists.
- **Graceful degrade.** Interactive verification is gated on XcodeBuildMCP tool presence (same detection pattern `design-mode.md` uses for Figma). Absent → fall back to today's static structural check; declared flows become `unverified_no_mcp` risks. Never fails the run.
- **Flows self-seed via taps.** A flow needing data includes its own setup steps ("add three habits, then open Stats"); no separate seed mechanism.
- **Verifier-driven (Approach A).** XcodeBuildMCP tools are added to `ios-visual-verifier`'s `tools:` list; the verifier drives its own simulator. Fan-out already allocates one `simulator_udid` per verifier task, which XcodeBuildMCP targets per-UDID. Keeps the role boundary intact (verifier verifies, never fixes) and barely touches the orchestrator.
- **Ships as v0.5.0** (0.4.0 issue-driven runs already merged).

## 1. Flow declaration (`design.md`, authored by the UI Designer)

Each screen's section in `docs/design.md` gains a `### Flows to verify` list. Each flow is a one-line NL goal (setup + action + expected outcome) plus a trailing environment tag:

```markdown
### Flows to verify
- **Set and start a goal** — open goal-setting, set the goal to 50, confirm the hero count shows a goal of 50. `sim`
- **Live jump counting** — with a workout active, the hero count increments as jumps are detected. `device` (needs AirPods head-motion, unavailable in Simulator)
```

- Tag `sim` (default) = drivable in the simulator. Tag `device` = needs real hardware.
- `agents/ios-ui-designer.md` gains a "Flows to verify" instruction: author 1–4 key flows per screen; tag a flow `device` when it depends on hardware the simulator lacks. The designer's `device` tags are informed by the Architect's hardware-related risks, which the orchestrator passes into the `ui_designer` dispatch (see §4). Self-seeding is expressed as setup steps inside a flow.

## 2. The verifier drives flows (`agents/ios-visual-verifier.md`, Approach A)

- Add XcodeBuildMCP tools to the verifier's `tools:` list. At the start of the `visual_verification` phase the orchestrator **detects** whether those tools are present (substring check on the session tool list, as `design-mode.md` does for `mcp__claude_ai_Figma__*`) and passes an `interactive: true|false` flag into each verifier dispatch.
- The verifier's work becomes two layers, in order:
  1. **Structural check (unchanged):** launch via the router, screenshot the target screen, structurally compare against the design reference. Always runs first.
  2. **Interactive flows (new, additive):** for each `sim`-tagged flow of this screen, drive the app — read the live UI (XcodeBuildMCP describe-UI/accessibility), decide the next tap/type/swipe toward the goal, execute it, screenshot each step into `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/step-N.png`, and assert the expected outcome by reading the final screen. A **step budget** of ≤12 actions per flow bounds a confused run so it reports instead of thrashing.
- **Per-flow verdict:** `pass` | `issues_found` | `deferred_to_device` (tagged `device`, never attempted in-sim) | `unverified_no_mcp` (XcodeBuildMCP absent → structural-only for that screen).
- The verifier's report gains a per-flow results list (flow name, verdict, step screenshots, and — for `issues_found` — the failing step and what was expected vs seen). When `interactive: false`, the verifier runs the structural check only and reports every declared flow as `unverified_no_mcp`.

## 3. Aggregate verdict and state (reuse the risk registry)

Per-flow outcomes are transient checkpoint inputs (like screenshots), not a new persisted structure. Two lean changes to `state.json` (see `state-schema.md`):

- A task's `results.verify_status` gains one value: **`deferred_to_device`** — meaning every `sim`-drivable flow passed but ≥1 `device` flow needs real-device confirmation. This keeps a plain `pass` honest. Precedence when aggregating a task's flows: any `issues_found` → `issues_found`; else any `device` flow → `deferred_to_device`; else `pass`. (`unverified_no_mcp` flows do not by themselves demote a `pass` to `issues_found`; they are recorded as risks — see below.)
- Flows that end `deferred_to_device` or `unverified_no_mcp` are recorded as **`open_risks`** entries (the pipeline already accumulates and surfaces these at every checkpoint). No new persisted schema — the risk registry is the correct home for "this wasn't verified, and here's why."

## 4. Orchestration — the loop and the device checkpoint (`orchestration-flow.md`, `checkpoints.md`)

- **`ui_designer` dispatch** additionally includes the Architect's hardware-related `open_risks` (so `device` tags are informed). This is the only new dispatch input on the design side.
- **`visual_verification` loop** keeps its 2-round structure. At phase start the orchestrator detects XcodeBuildMCP and sets `interactive` for the verifier dispatches. A flow `issues_found` routes to the developer via the existing `address_visual` dispatch (with the failing-flow findings + step screenshots) and re-verifies in round 2 — identical machinery to today's structural findings. `device` flows are recorded `deferred_to_device`, never looped on.
- **Device checkpoint:** at the `visual_verification` checkpoint, when any flow is `deferred_to_device`, the orchestrator surfaces a real-device hand-off via `AskUserQuestion`: "These flows need a real device: [list]. Run them and report, or defer?"
  - **Report result** → the orchestrator records pass (removing the corresponding risk) or fail (→ an `address_visual` fix if actionable, else a carried risk).
  - **Defer** → the flow stays an `open_risk` (pending device), and the run continues. **Non-blocking** — never a hard stop, matching the resumable checkpoint model.
- **MCP absent** → the checkpoint summary notes "connect XcodeBuildMCP for interactive verification," and every declared flow is an `unverified_no_mcp` risk.

## 5. Checkpoint presentation (`checkpoints.md`)

The `visual_verification` checkpoint summary additionally lists, per task, each flow and its verdict (`pass`/`issues_found`/`deferred_to_device`/`unverified_no_mcp`) with the step-screenshot path, and — when any `deferred_to_device` flow exists — presents the real-device hand-off prompt from §4. Existing structural-verdict content is unchanged.

## 6. Error handling (all soft-fail)

- XcodeBuildMCP absent → structural-only, flows `unverified_no_mcp`; never an error.
- Flow can't complete (control not found, app crashes mid-flow) → `issues_found` with the failing step + screenshot; the step budget prevents thrashing.
- Simulator dies mid-flow → `skipped` (infra), exactly as today's skip handling.
- Verifier can't decide the next action after bounded attempts → `issues_found` if it's an app defect, or a risk if the *flow spec itself* is ambiguous (lead with which).
- Router miss (screen unreachable) → today's behavior: verify root only + risk; that screen's flows become `unverified` risks, never false findings.

## 7. Affected documents

- `agents/ios-visual-verifier.md` — add XcodeBuildMCP tools to `tools:`; the two-layer structural-then-interactive procedure; step budget; the four per-flow verdicts; report format gains per-flow results; `interactive` dispatch flag.
- `agents/ios-ui-designer.md` — author `### Flows to verify` per screen with `sim`/`device` tags, informed by the Architect's hardware risks.
- `skills/ios-genesis/references/interactive-verification.md` — **new**; the flow protocol, XcodeBuildMCP detection, step budget, the four verdicts, the device hand-off, and degrade behavior.
- `skills/ios-genesis/references/orchestration-flow.md` — `ui_designer` dispatch passes hardware risks; `visual_verification` loop gains MCP detection, the `interactive` flag, flow inputs, and the device checkpoint.
- `skills/ios-genesis/references/state-schema.md` — `results.verify_status` gains `deferred_to_device`; note that deferred/unverified flows are recorded as `open_risks`.
- `skills/ios-genesis/references/checkpoints.md` — the `visual_verification` checkpoint presents per-flow verdicts and the real-device hand-off prompt.
- `skills/ios-genesis/SKILL.md` — reference the new doc.
- `README.md` — document interactive verification; retire/soften the "no in-screen interaction" known limitation (now addressed behind XcodeBuildMCP).
- `.claude-plugin/plugin.json` — version bump to `0.5.0`.

No `agents/ios-architect.md` edit — it already raises hardware risks; the orchestrator routes them to the designer via the `ui_designer` dispatch.

## 8. Deferred (explicitly out of scope for v0.5.0)

- **XCUITest-codegen fallback** — generating XCUITest flow tests when no MCP is present.
- **A Finding-A UX-completeness *reasoning* agent** — this feature lets the verifier *walk* an authored onboarding flow, but does not add an agent that invents missing states/screens.
- **The Claude Desktop simulator-pane path** — this feature uses XcodeBuildMCP (agent-drivable); the Desktop pane is human-adjacent and noted for the future.
- **Declaring flows in the task graph** — flows live in `design.md`, not `state.json`'s `task_graph`.
- **Non-visual (`feature`/foundation-only) tasks** — interactive verification applies to `ui_impact: true` tasks, exactly like the existing visual_verification projection.

## Validation plan

- `feature_addition`/`new_app` with XcodeBuildMCP connected and `screens_affected: true`: confirm the verifier runs the structural check then drives each `sim` flow, saves step screenshots under `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/`, and asserts outcomes; a `device`-tagged flow yields `deferred_to_device` and the checkpoint shows the real-device hand-off (verify both the report-result and defer paths, incl. the `open_risks` bookkeeping).
- Same run **without** XcodeBuildMCP: confirm graceful degrade — structural check only, every declared flow recorded `unverified_no_mcp`, run completes, checkpoint notes the missing MCP.
- Inject a UI bug that breaks a flow's assertion: confirm `issues_found` → `address_visual` → round-2 resolution, mirroring today's structural-finding loop.
- Cadenza is the natural target: its welcome/onboarding flow is `sim`-drivable; the AirPods counting flow is `device`-gated (`deferred_to_device`).
- Scope check: touches `agents/{ios-visual-verifier,ios-ui-designer}.md`, `skills/ios-genesis/**`, `README.md`, `.claude-plugin/plugin.json` — no Swift, no new agent files.
