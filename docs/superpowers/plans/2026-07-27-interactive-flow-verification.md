# Interactive-Flow Verification Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `ios-visual-verifier` drive the app in the simulator via XcodeBuildMCP (tap/type/read-UI) to verify per-screen NL flows authored by the UI Designer, with a distinct `deferred_to_device` verdict + real-device checkpoint for hardware-gated flows, and graceful degrade when XcodeBuildMCP is absent.

**Architecture:** Documentation-only — no Swift, no new agents. The UI Designer authors `### Flows to verify` per screen in `design.md`; the verifier (given a new `interactive` flag and XcodeBuildMCP tools) runs its existing structural check then drives each `sim` flow, reporting per-flow verdicts + a `flow_results` list and a top-level `status` that gains `deferred_to_device`. Deferred/unverified flows ride the existing `open_risks` registry; the `visual_verification` checkpoint gains a real-device hand-off. A new `references/interactive-verification.md` is the canonical protocol home.

**Tech Stack:** Markdown reference docs + two agent files (`agents/ios-visual-verifier.md`, `agents/ios-ui-designer.md`) for the ios-genesis plugin, plus `README.md` and `.claude-plugin/plugin.json`. No unit tests — each task is a doc edit verified by `grep` + coherence read; validated end-to-end by a manual run (final task).

**Spec:** `docs/superpowers/specs/2026-07-27-interactive-flow-verification-design.md` (approved, review round 2).

**Working branch:** `feature/interactive-flow-verification` (created off `main` @ 0.4.0; spec already committed here).

**Verification note:** run `grep` from repo root `/Users/giorgiamarenda/Projects/iOSOrchestator`. "The test" for each task is a `grep` that the anchor text exists + a coherence read.

---

## Chunk 1: Producer side — protocol doc, designer authoring, verifier driving

### Task 1: Create `references/interactive-verification.md`

**Files:**
- Create: `skills/ios-genesis/references/interactive-verification.md`

- [ ] **Step 1: Write the canonical protocol doc**

Create `skills/ios-genesis/references/interactive-verification.md`:

```markdown
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
```

- [ ] **Step 2: Verify**

Run: `grep -c "^## " skills/ios-genesis/references/interactive-verification.md`
Expected: `7` (Detection, Flow declaration, Driving a flow, Verdicts, Device checkpoint, Degrade, Error handling).

Run: `grep -n "describe_ui\|deferred_to_device\|unverified_no_mcp\|step budget\|interactive: true\|flow-<slug>" skills/ios-genesis/references/interactive-verification.md`
Expected: all present.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/interactive-verification.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "Add interactive-verification reference doc"
```

### Task 2: UI Designer authors `### Flows to verify`

**Files:**
- Modify: `agents/ios-ui-designer.md` (the design-structure template ~lines 31-45; the "Your input" list ~lines 12-21)

- [ ] **Step 1: Add `hardware_risks` to the input list**

After the `architecture_summary` input bullet (line 14), add:
```markdown
- `hardware_risks` (optional): a summary of the Architect's hardware-related risks (e.g. a sensor or capability unavailable in the iOS Simulator), used to tag flows `device` in the "Flows to verify" list below.
```

- [ ] **Step 2: Add `### Flows to verify` to the design-structure template**

In the ```` ```markdown ```` design-structure block, immediately after the `- View hierarchy:` sub-block of `### <ScreenName>` (before `## Navigation Flow`), add:
```markdown
- Flows to verify:
  - <one-line NL goal: setup + action + expected outcome> `sim`
  - <a flow that needs real hardware> `device`
```

- [ ] **Step 3: Add the authoring instruction**

At the end of the design-structure section (right before `## Mode-specific behavior`, line 49), add a paragraph:
```markdown
**Flows to verify.** For every screen, author 1-4 key user flows the Visual Verifier should drive to confirm the screen works, not just renders — each a one-line natural-language goal (setup + action + expected outcome). Tag each flow `sim` (drivable in the Simulator) or `device` (needs real hardware the Simulator lacks — e.g. motion/AirPods sensors, camera). Use `hardware_risks` from your dispatch to decide which flows are `device`. A flow that needs data should include its own setup steps ("add three habits, then open Stats and confirm the rows render"). See `references/interactive-verification.md`.
```

- [ ] **Step 4: Verify**

Run: `grep -n "Flows to verify\|hardware_risks\|interactive-verification" agents/ios-ui-designer.md`
Expected: input bullet, template block, instruction paragraph, and the doc reference all present.

- [ ] **Step 5: Commit**

```bash
git add agents/ios-ui-designer.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "ios-ui-designer: author per-screen Flows to verify (sim/device tags)"
```

### Task 3: Verifier drives flows

**Files:**
- Modify: `agents/ios-visual-verifier.md` (`tools:` frontmatter line 4; the "Your input" list ~lines 18-35; a new "Interactive flow verification" section after the Solo-mode steps ~line 58; the report block ~lines 64-74)

- [ ] **Step 1: Add XcodeBuildMCP tools to `tools:`**

Change the frontmatter `tools:` line from:
```
tools: Read, Bash, WebFetch, mcp__claude_ai_Figma__get_screenshot
```
to:
```
tools: Read, Bash, WebFetch, mcp__claude_ai_Figma__get_screenshot, mcp__XcodeBuildMCP__describe_ui, mcp__XcodeBuildMCP__tap, mcp__XcodeBuildMCP__type_text, mcp__XcodeBuildMCP__swipe, mcp__XcodeBuildMCP__screenshot
```
(Note in the commit body: the `mcp__XcodeBuildMCP__` prefix is the expected default registration; if the user's XcodeBuildMCP registers under a different prefix, detection is by tool basename per `references/interactive-verification.md`, and the `tools:` entries should match the actual registered names.)

- [ ] **Step 2: Add the `interactive` input**

In "## Your input", after the `verification_round` bullet, add:
```markdown
- `interactive`: `true` if XcodeBuildMCP is connected this run (the orchestrator detected it — see `references/interactive-verification.md`), enabling flow-driving; `false` means structural-only.
```

- [ ] **Step 3: Add the interactive-flow section**

After the Solo-mode steps (before "## Your final report to the orchestrator"), add:
```markdown
## Interactive flow verification

After the structural check above (fan-out step 4 / solo step 6), if `interactive: true`, drive each `sim`-tagged flow in the screen's `### Flows to verify` list (from `design_summary`). Use the same UDID the structural check used (fan-out: `simulator_udid`; solo: the UDID you booted). Per `references/interactive-verification.md`: read the UI with `describe_ui`, decide and execute the next `tap`/`type_text`/`swipe` toward the goal, `screenshot` each step to `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/step-N.png` (solo: omit `<task_id>/`), and assert the expected outcome. Budget: <=12 actions per flow, then stop and report.

Per-flow verdict: `pass` | `issues_found` (flow blocked or assertion failed — cite the step) | `deferred_to_device` (flow tagged `device`; never drive it in-sim) | `unverified_no_mcp` (only when `interactive: false` — every declared flow gets this and you run the structural check only).

Roll the flows up into the report's top-level `status`: any `issues_found` -> `issues_found`; else any `deferred_to_device` -> `deferred_to_device`; else `pass`. `unverified_no_mcp` flows never change `status` (the structural result stands); they appear in `flow_results` and are recorded as risks by the orchestrator.
```

- [ ] **Step 4: Extend the report block**

In "## Your final report to the orchestrator", change the `status` line from:
```
- status: <pass|issues_found|skipped>
```
to:
```
- status: <pass|issues_found|skipped|deferred_to_device>
```
and, after the `findings` line, add:
```
- flow_results: <one entry per declared flow — flow name, verdict (pass|issues_found|deferred_to_device|unverified_no_mcp), its flow-<slug>/ step screenshot paths, and for issues_found the failing step + expected-vs-seen — or "none" if the screen declared no flows>
```

- [ ] **Step 5: Verify**

Run: `grep -n "mcp__XcodeBuildMCP__tap\|Interactive flow verification\|flow_results\|deferred_to_device\|interactive" agents/ios-visual-verifier.md`
Expected: tools entry, the new section, the report field, the status value, and the input bullet all present.

Run: `grep -c "deferred_to_device" agents/ios-visual-verifier.md`
Expected: `>=3` (interactive section rollup, status line, flow_results line).

- [ ] **Step 6: Commit**

```bash
git add agents/ios-visual-verifier.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "ios-visual-verifier: drive sim flows via XcodeBuildMCP + flow_results/deferred_to_device"
```

## Chunk 2: Orchestration, state, checkpoints, wiring, version, validation

### Task 4: Orchestration — dispatch inputs, MCP detection, status branch, device checkpoint

**Files:**
- Modify: `skills/ios-genesis/references/orchestration-flow.md` (the `ui_designer` fan-out mechanics ~line 40 and steps 2 ~lines 73/86; the `visual_verification` fan-out mechanics ~lines 55-59; the "Visual verification loop" section ~lines 95-108)

- [ ] **Step 1: Pass hardware risks into the ui_designer dispatch**

In the `### ui_designer` fan-out mechanics paragraph (line 40, the sentence listing fan-out dispatch prompt fields), add `hardware_risks` to the listed inputs, e.g. append to that sentence:
```markdown
 Every ui_designer dispatch (solo and fan-out) also includes `hardware_risks`: a summary of the Architect's hardware-related `open_risks` (capabilities unavailable in the Simulator), so the designer can tag flows `device` (see `references/interactive-verification.md`).
```

- [ ] **Step 2: Add MCP detection + interactive flag to the visual_verification mechanics**

In the `### visual_verification` fan-out mechanics (after line 57, the build-once/install bullet), add:
```markdown
- **Interactive-flow detection (once, at phase start):** check the session tool list for XcodeBuildMCP automation tools (a tool ending `__describe_ui` and one ending `__tap`, prefix-independent — see `references/interactive-verification.md`). Set `interactive: true|false` and pass it into every verifier dispatch this phase (both fan-out and solo). Absent -> the verifier runs structural-only and every declared flow becomes an `unverified_no_mcp` `open_risk`.
```

- [ ] **Step 3: Add the `interactive` input + status branch + device checkpoint to the loop**

In the "## Visual verification loop" section: (a) in the "Dispatch inputs for `ios-visual-verifier`" sentence (line 99), add `interactive` to the listed inputs; (b) after the `status: skipped` handling (step 3, line 103), add a new branch:
```markdown
3b. `status: deferred_to_device` (all `sim` flows passed, >=1 `device` flow) -> do not loop. Record each deferred flow as an `open_risks` entry, and at the checkpoint present the real-device hand-off (`AskUserQuestion`: run the listed device flows and report, or defer). Report a result -> resolve the risk (pass) or dispatch `address_visual` / carry a risk (fail). Defer -> the flow stays an `open_risk` (pending device). Non-blocking. See `references/interactive-verification.md`.
```
and in step 4a (issues_found handling), add a sentence: `A flow whose assertion failed is an issues_found finding like any structural finding — routed to address_visual with the flow's failing step + flow-<slug>/ screenshots.`

- [ ] **Step 4: Verify**

Run: `grep -n "hardware_risks\|interactive\|deferred_to_device\|interactive-verification" skills/ios-genesis/references/orchestration-flow.md`
Expected: the dispatch input, detection bullet, loop input, the status branch, and doc references all present.

- [ ] **Step 5: Commit**

```bash
git add skills/ios-genesis/references/orchestration-flow.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "orchestration-flow: interactive detection, hardware_risks dispatch, device checkpoint"
```

### Task 5: State schema — `deferred_to_device`

**Files:**
- Modify: `skills/ios-genesis/references/state-schema.md` (the `verify_status` value set, in the `results` field description ~line 106)

- [ ] **Step 1: Add the value + the open_risks note**

Change `verify_status`: `pass|issues_found|skipped` to `verify_status`: `pass|issues_found|skipped|deferred_to_device` in the `results` field description, and append to that clause:
```markdown
 (`deferred_to_device` means every `sim`-drivable flow passed but a `device`-tagged flow needs real-device confirmation — see `references/interactive-verification.md`; the deferred flow, and any `unverified_no_mcp` flow, is also recorded as an `open_risks` entry rather than a new persisted field).
```

- [ ] **Step 2: Verify**

Run: `grep -n "deferred_to_device" skills/ios-genesis/references/state-schema.md`
Expected: present in the `verify_status` value set + the explanatory note.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/state-schema.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "state-schema: verify_status gains deferred_to_device"
```

### Task 6: Checkpoints — present flow results + device hand-off

**Files:**
- Modify: `skills/ios-genesis/references/checkpoints.md` (step 5, the `visual_verification` summary sentence ~line 51)

- [ ] **Step 1: Extend the visual_verification checkpoint summary**

Append to the `visual_verification` summary sentence (the one ending "list any screens the verifier reported as `unverified`."):
```markdown
 When flows were verified (see `references/interactive-verification.md`), also list each flow and its verdict (`pass`/`issues_found`/`deferred_to_device`/`unverified_no_mcp`) with its `flow-<slug>/` screenshot path; and when any flow is `deferred_to_device`, present the real-device hand-off prompt (run the listed device flows and report, or defer).
```

- [ ] **Step 2: Verify**

Run: `grep -n "deferred_to_device\|flow.*verdict\|interactive-verification" skills/ios-genesis/references/checkpoints.md`
Expected: the new sentence present.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/checkpoints.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "checkpoints: present flow verdicts + device hand-off at visual_verification"
```

### Task 7: Reference the new doc in `SKILL.md`

**Files:**
- Modify: `skills/ios-genesis/SKILL.md` (the "## Reference docs" list)

- [ ] **Step 1: Add the list entry**

After the `references/issue-driven-runs.md` line, add:
```markdown
- `references/interactive-verification.md` - driving the app in the simulator (tap/type/read-UI via XcodeBuildMCP) to verify per-screen flows, with a real-device hand-off for hardware-gated flows
```

- [ ] **Step 2: Verify**

Run: `grep -n "interactive-verification.md" skills/ios-genesis/SKILL.md`
Expected: one hit in the Reference docs list.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/SKILL.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "SKILL: reference interactive-verification doc"
```

### Task 8: Update `README.md`

**Files:**
- Modify: `README.md` (the "No in-screen interaction" bullet in "## Known limitations & roadmap")

- [ ] **Step 1: Soften/retire the limitation bullet**

Replace the "No in-screen interaction" bullet (which names XcodeBuildMCP as "the next milestone") with:
```markdown
- **In-screen interaction (opt-in).** When XcodeBuildMCP is connected, the visual verifier drives the app in the simulator — tapping, typing, and reading the UI to verify per-screen *flows* the UI Designer declares in `docs/design.md`, not just the launch screen. Flows that need real hardware (e.g. motion sensors) are tagged `device`, get a distinct `deferred_to_device` verdict, and are handed off to you for on-device confirmation at the checkpoint. Without XcodeBuildMCP, verification gracefully degrades to the structural launch-screen check.
```

- [ ] **Step 2: Verify**

Run: `grep -n "In-screen interaction (opt-in)\|deferred_to_device" README.md`
Expected: the new bullet present.

Run: `grep -c "No in-screen interaction" README.md`
Expected: `0` (old bullet removed).

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "README: document interactive flow verification"
```

### Task 9: Bump plugin version to 0.5.0

**Files:**
- Modify: `.claude-plugin/plugin.json`

- [ ] **Step 1: Bump the version**

Change `"version": "0.4.0"` to `"version": "0.5.0"`.

- [ ] **Step 2: Verify**

Run: `grep '"version"' .claude-plugin/plugin.json`
Expected: `"version": "0.5.0"`.

Run: `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "Bump plugin to 0.5.0 (interactive flow verification)"
```

### Task 10: Manual end-to-end validation

**No file changes** — a manual run, driven by Giorgia (the plugin is validated by real runs). Requires XcodeBuildMCP installed and connected in the session. Cadenza (`~/Projects/scratch/Cadenza`) is the natural target: its welcome/onboarding flow is `sim`-drivable; the AirPods counting flow is `device`-gated.

- [ ] **Step 1: Reinstall the 0.5.0 plugin** (the version-cache dance)

```
/plugin marketplace update ios-orchestrator
/plugin uninstall ios-genesis@ios-orchestrator
/plugin install ios-genesis@ios-orchestrator
```
Restart; confirm `/plugin` reads **0.5.0**.

- [ ] **Step 2: Connect XcodeBuildMCP** in the session and confirm its tools are present (a `*__describe_ui` and `*__tap` tool).

- [ ] **Step 3: Interactive path** — run a `feature_addition`/`new_app` with `screens_affected: true`. Confirm: the UI Designer authored `### Flows to verify` in `docs/design.md`; the verifier ran the structural check then drove each `sim` flow; step screenshots saved under `.ios-orchestrator/screenshots/<task_id>/flow-<slug>/`; assertions reported per-flow in `flow_results`.

- [ ] **Step 4: Device-gated path** — confirm a `device`-tagged flow yields `deferred_to_device`, the checkpoint shows the real-device hand-off, and both report-result (resolves the risk) and defer (keeps the `open_risk`) paths work.

- [ ] **Step 5: Degrade path** — run with XcodeBuildMCP NOT connected. Confirm structural-only verification, every declared flow recorded as an `unverified_no_mcp` `open_risk`, the checkpoint notes the missing MCP, and the run completes.

- [ ] **Step 6: Fix loop** — inject a UI bug that breaks a flow's assertion; confirm `issues_found` -> `address_visual` -> round-2 resolution.

- [ ] **Step 7: Scope check** — confirm the diff touched only `agents/{ios-visual-verifier,ios-ui-designer}.md`, `skills/ios-genesis/**`, `README.md`, and `.claude-plugin/plugin.json` — no Swift, no new agent files.

---

## Execution notes

- Commit after each task; all commits authored as `Claude Fable 5`.
- After Chunk 1 and Chunk 2, run the plan-document-reviewer loop before execution handoff.
- When ready to ship: open a PR from `feature/interactive-flow-verification` to `main`; Giorgia runs the reinstall dance (Task 10 Step 1) to receive 0.5.0. XcodeBuildMCP is a new runtime prerequisite for the interactive path — note it in the PR.
