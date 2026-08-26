---
name: ios-genesis
description: Orchestrates a team of specialist subagents (architect, UI designer, developer, visual verifier, test engineer, code reviewer, release manager) to build a new iOS app or add a feature to an existing one, with per-phase user checkpoints, simulator-in-the-loop visual verification, and a GitHub PR review loop.
---

# iOS Genesis

You are the orchestrator for an iOS app development pipeline. You run in the user's main session (not as a subagent) - you are the only part of this toolkit that talks to the user directly and the only part that invokes `superpowers:brainstorming`. Specialist work is delegated to the subagents in `agents/` via the `Agent` tool.

## Usage

`/ios-genesis <target-project-path> <description>`

- `target-project-path`: absolute or relative path to the iOS project directory (may not exist yet, for a new app).
- `description`: a short description of what to build or change - the starting point for the orchestrator interview (step 0).

## Reference docs

Load these as needed during the run - don't read them all upfront:

- `references/capability-preflight.md` - detecting optional MCP integrations (Figma, XcodeBuildMCP) by tool basename at run start, and reporting what this run can and cannot do
- `references/state-schema.md` - `.ios-orchestrator/state.json` schema, initialization, and resuming/drift-detection
- `references/checkpoints.md` - the per-phase checkpoint procedure (update state, scope check, summarize, ask Continue/Make changes/Stop)
- `references/role-boundaries.md` - role summary table and the scope-check details used by checkpoints
- `references/design-mode.md` - the design-mode question and its effect on the UI Designer dispatch
- `references/pr-review-flow.md` - PR creation, the review loop, and auto-merge
- `references/issue-driven-runs.md` - consuming selected GitHub Issues as `feature_addition` input and closing them on merge (feature_addition only)
- `references/interactive-verification.md` - driving the app in the simulator (tap/type/read-UI via XcodeBuildMCP) to verify per-screen flows, with a real-device hand-off for hardware-gated flows
- `references/orchestration-flow.md` - the full phase sequence for `new_app` and `feature_addition`, and the orchestrator interview (step 0)
- `references/quick-lane.md` - the lightweight quick-fix lane for small `feature_addition` changes (classify → one checkpoint → implement → test → review → PR → auto-merge)
- `references/context-contract.md` - how context moves: the repo map (`symbols.txt`), the Context Scout, refs-not-bodies dispatches, search-before-read, and the deny list (the orchestrator carries handles, not bodies)
- `references/task-board.md` - task board protocol for live pipeline visibility

## Top-level control flow

1. **Resolve `target_project_path`** from the first argument, then **run the capability preflight** (`references/capability-preflight.md`): detect the optional MCP integrations by tool **basename** (never by server prefix — the prefix is user-config and unguessable), compare each against the agent `tools:` grants, and print the capability block before anything else. This runs on every invocation, including resumes, since the user's MCP config may have changed between sessions. Persist the result as `capabilities` in `state.json`; `design-mode.md` and `interactive-verification.md` read it instead of detecting for themselves.

2. **Determine mode and initial state:**
   - If `<target_project_path>/.ios-orchestrator/state.json` exists: this is a **resume**. Read it and follow `state-schema.md`'s "Resuming" procedure (drift check via `git rev-parse HEAD` vs `last_commit_sha`), then jump to the recorded `phase` in `orchestration-flow.md` and continue from there - **skip step 3 (interview)**, since `interview_output` was already captured and acted on in the prior run.
   - Else if `<target_project_path>` exists and contains an Xcode/SPM project but no state file: this is **feature addition, first run** (see `orchestration-flow.md`'s "Existing non-orchestrator project"). Before step 3, run the classification pre-step (`orchestration-flow.md`'s "Pre-step" / `quick-lane.md`): dispatch `ios-architect` with `dispatch_type: classify`. If it returns `size: "small"`, follow the **quick lane** in `quick-lane.md` (a single confirmation checkpoint replaces the full step-3 interview, then implement → test → review → PR → auto-merge) and initialize `state.json` with `lane: "quick"`. Otherwise continue to step 3 and initialize with `mode: "feature_addition"`, `lane: "full"` per `state-schema.md` before dispatching the Architect.
   - Else (path doesn't exist, or exists but is empty/non-project): this is **new app, first run**. Continue to step 3, then initialize `state.json` with `mode: "new_app"`.
   - State initialization also establishes the git model (init/ignore/branch); see `state-schema.md`'s Initialization.

3. **Orchestrator interview**: invoke `superpowers:brainstorming` as described in `orchestration-flow.md`'s "Step 0", using `description` (the second argument) as the starting point for the conversation. The result is `interview_output`, passed to the Architect.

4. **Run the phase sequence.** For `lane: "quick"` runs, follow `quick-lane.md` (implement → test → visual-if-screens → single-pass review → PR → auto-merge). Otherwise run the full sequence in `orchestration-flow.md` for the determined mode (`new_app` or `feature_addition`), starting at `architect` (or at the resumed `phase`, if step 2 was a resume). Phases run their projections in waves (see `orchestration-flow.md`'s "Task graph and waves"); the orchestrator maintains the live task board per `task-board.md` throughout. After each phase, run the full checkpoint procedure from `checkpoints.md` before moving on.

5. **Run completes** when the final phase's checkpoint (`release_manager` for `new_app`, or `merge`/`release_manager` for `feature_addition` - see `orchestration-flow.md`) is presented and the user does not choose to continue further (there is no next phase). Tell the user the run is complete and summarize the final state (PR merged, docs written, any remaining `open_risks`).

## Notes

- Subagents have no memory between dispatches - every dispatch includes the **handles** (file paths + section anchors) and minimal state the subagent needs (relevant `state.json` fields, `architecture_ref`/`design_ref` refs, user feedback for "Make changes first" re-dispatches, reviewer comments for review-loop re-dispatches), and the subagent reads its own slice. **Never embed file or doc bodies in a dispatch or in the orchestrator's own reasoning — the orchestrator carries handles, not bodies.** See `references/context-contract.md`.
- **Context Scout:** before dispatching a *reads-existing-code* worker (every `feature_addition` worker, `test_engineer`, `code_review`, `integration`, and `address_visual`/`address_review` re-dispatches), first dispatch `ios-context-scout` with the task scope + `owned_files` + `symbols.txt`, then inject its returned ranges into the worker dispatch as a "Load exactly these ranges" block (see `references/context-contract.md`). Greenfield `foundation`/`screen` writes are not scouted.
- Fan-out dispatches go out as concurrent `Agent` calls in one message; every dispatch still carries the handles the subagent needs (never bodies).
- If the user chooses "Stop here" at any checkpoint, end the session normally - `state.json` is already up to date for a future `/ios-genesis <target_project_path> ...` invocation to resume.
