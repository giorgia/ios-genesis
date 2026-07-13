# Orchestration Flow

This is the phase sequence the orchestrator follows once it has determined the mode (`new_app` or `feature_addition`) and initialized/loaded `state.json` (see `state-schema.md`). State initialization also establishes the git model — the repo, the `.ios-orchestrator/`-ignoring `.gitignore`, the initial commit, and the working branch all exist before the Architect ever runs, and all run commits land on the working branch until `merge`; the procedure lives in `state-schema.md`'s Initialization section. After every phase, run the full checkpoint procedure in `checkpoints.md` (which includes the scope check from `role-boundaries.md`) before moving to the next phase.

## Step 0 (both modes): Orchestrator interview

The orchestrator (running in the user's main session) invokes the `superpowers:brainstorming` skill itself to interview the user about what's being built/changed:

- Follow the brainstorming skill through design approval: explore project context, optionally offer the visual companion (not expected in this CLI-driven context and can be left declined/skipped), ask clarifying questions one at a time, propose 2-3 approaches with trade-offs, then present the design in sections until the user approves it.
- **Never ask for design approval without the design itself in the same message.** Before any "Does this design look right?" question, print the full assembled design — screen content and behavior, chosen approach, and how the interview answers were incorporated. Collapsing the approach choice into an option label and then asking for approval of an unshown design is a checkpoint violation (the user would be approving content they never saw).
- **Adapted terminal steps**: once the design is approved, do NOT write a spec document to `docs/superpowers/specs/`, run a spec-review loop, ask the user to review a written spec, or invoke `writing-plans` - this orchestration flow IS the implementation plan, so skip all of brainstorming's remaining post-approval checklist items.
- The approved interview output (requirements, chosen approach, design summary) becomes `interview_output`, persisted to `state.json` at initialization (see `state-schema.md`) and passed to the Architect in step 1.
- For `feature_addition` against an existing project with no state file (see "Existing non-orchestrator project" below), do this interview *before* initializing `state.json`, so the Architect's first dispatch can include both `interview_output` and the codebase-survey instruction.

## Task graph and waves

The Architect **returns** the task graph in its report; the orchestrator validates it — ownership disjointness and that `depends_on` forms a DAG (a cycle would deadlock the wave scheduler) — and on a validation failure re-dispatches the Architect with the defect named, at most twice, then surfaces the problem to the user at the checkpoint. On acceptance the orchestrator persists the graph as `state.json`'s `task_graph` (field definitions and the dual-mode round-counter rule: `state-schema.md`) and creates the task board (`task-board.md` — which also covers the per-phase board that single-task graphs get instead).

**Phase projection.** Each phase computes its working set from the graph:

| Phase | Works on |
|---|---|
| ui_designer | tasks with `ui_impact: true` |
| developer | all tasks (foundation solo → screens/features in waves → integration solo) |
| visual_verification | tasks with `ui_impact: true` |
| test_engineer | registration pre-step, then `foundation` + `screen` + `feature` tasks (foundation's models get dedicated tests) |
| pr_creation / code_review / merge / release_manager | whole-run (no fan-out, unchanged) |

`depends_on` edges are evaluated **within the projection**: a dependency with no work in the current phase, or one whose `status` is `dropped`, counts as satisfied.

**Waves.** A wave is the set of currently unblocked tasks in the projection, at most `cap` at a time, dispatched as **concurrent subagent calls in a single message**. Siblings always run to completion; when every agent in the wave has reported, run the phase's wave-end steps (see the per-phase mechanics below), then dispatch the next wave, until the projection is exhausted — then the post-phase checkpoint fires (`checkpoints.md`, including per-task failure resolution and the next phase's wave preview). When a task exhausts its failure rounds, the phase concludes early (dependent waves not yet run) and the checkpoint fires; retry/drop re-enters the wave scheduler, so the checkpoint can legitimately fire again after the remaining waves complete (see `checkpoints.md` step 3). Update the task board on every dispatch and report (`task-board.md`). **Single-task graphs** degenerate to the v0.2.0 sequential flow: the numbered steps below read as written, with no wave machinery.

## Fan-out mechanics per phase

**Design principle:** in a single shared Xcode target, *compilation is inherently an integration act* — a build sweeps in every file present, including siblings' work-in-progress. Fan-out therefore parallelizes **writing**, and treats **building as a serial, orchestrator-run integration step** at wave end. No agent builds concurrently with another agent's unfinished code.

### ui_designer

One agent per projected task (`ui_impact: true`). Each agent **returns its design section in its report**; the orchestrator assembles `docs/design.md` (single writer). Fan-out dispatch prompts include: `task_id`, the task's `title`, `owned_files` (so the agent knows its scope), the screens assigned to this task (from the architecture), `design_mode`, and — for `bring_your_own` — this task's mapped `design_sources` entries. Solo dispatch prompts (single-task graph) include none of the task fields (`task_id`, `title`, `owned_files`, screen scope). Per design mode:

- `figma`: each task's mockup is its own Figma file; the link is stored in that task's `results.design_reference` and passed to that task's verifier. The assembled `docs/design.md` lists per-screen Figma links instead of one.
- `claude_design`: per-task paste summaries, concatenated by the orchestrator into one user handoff at the checkpoint.
- `bring_your_own`: after `design_mode` resolves to `bring_your_own` on a multi-task graph, the **orchestrator** maps each entry in `design_sources` to a task (matching by screen/feature name; on ambiguity, ask the user via `AskUserQuestion`) and writes each task's `results.design_reference` before dispatching the ui_designer wave. The Architect performs this mapping only when `design_sources` is already present in its dispatch (resumed runs where `design_mode` was set in a previous session).

### developer — write in parallel, build as integration

- Every developer task-graph dispatch prompt (multi-task graphs only; single-task-graph dispatches carry none of these fields and keep the v0.2.0 solo contract) includes the task's `task_id`, `kind` (from the graph), and `owned_files`; edits outside them are forbidden (foundation outputs are read-only context for screen/feature agents). The same applies to the test engineer's fan-out task dispatches. **Fan-out wave agents do not build** — they write code, using at most `swiftc -typecheck <own files>` for a best-effort local sanity pass.
- **Wave-end integration build (orchestrator, serial):** when all wave agents report, run `xcodegen generate` once, then `xcodebuild build` once. This is the only regeneration and the only build for the wave.
- **Build-failure routing:** compile errors are attributed to tasks by file ownership, and the owning agents are re-dispatched with their errors (concurrently, if several tasks failed). Up to 3 wave-build rounds; still-failing tasks are marked `failed` and surface at the checkpoint per `checkpoints.md`'s failure policy. Errors in files no task owns are surfaced at the checkpoint as an integration defect.
- On wave-build success: `wip(developer/wave-N)` commit; attribution/scope check via `git diff --name-only <previous wip commit>` mapped to owned-path prefixes (see `role-boundaries.md`); unattributable paths are flagged at the checkpoint.
- **Solo waves** (foundation, integration, and every single-task graph) keep the v0.2.0 agent behavior: the agent builds itself, up to 3 attempts.
- `project.yml` edits are reserved to `foundation`/`integration` tasks by construction (glob `sources` make screen/feature file additions invisible to it).

### visual_verification

- Code is frozen by this phase, so the orchestrator **builds once** and `simctl install`s the same `.app` onto one simulator per verifier task — each verifier gets its own UDID, allocated from `simctl list devices available`. Fewer available devices than `cap` → smaller waves (a rule that applies equally to test_engineer's parallel `test-without-building` runs). Fan-out verifiers do not build — they launch, screenshot, and compare; the single-task/sequential path keeps v0.2.0 behavior (the verifier builds).
- **Screen reachability (router):** the `foundation` task adds the debug-only router *mechanism* (`-ios-genesis-screen <Name>`, behind `#if DEBUG`); the `integration` task adds the *registry* entries once screens exist. Screens register under their `docs/design.md` screen names (the canonical display name from the design document, e.g. "Home", "Settings Detail"). Verifiers launch via `simctl launch <udid> <bundle> -ios-genesis-screen <Name>`. Foundation-owns-the-mechanism is the `new_app` framing; in `feature_addition` the router mechanism ships inside the *integration* task, and only when the graph has verifier work. If the app lacks the router and the graph has no integration task, verification falls back to root-screen-only plus an `open_risks` entry naming the gap — never a hard failure.
- The per-task loop keeps v0.2.0 semantics — 2 rounds, `address_visual` re-dispatch (see the Visual verification loop below); round counters follow `state-schema.md`'s dual-mode rule (top-level `verification_round` on single-task graphs, per-task `results.verification_round` otherwise). If several tasks' `address_visual` fixes land concurrently, they re-enter the wave-end integration-build rule above.

### test_engineer

- **Registration pre-step (serial, once):** if test targets are missing, a single dispatch registers them in `project.yml` + `xcodegen generate` — the one sanctioned shared-file edit, with no siblings running. The orchestrator dispatches `ios-test-engineer` with `dispatch_type: register_targets` for this step.
- **Write in parallel, build once, run in parallel:** wave agents write test files into per-task test directories without running them. Each fan-out write dispatch includes `task_id`, `kind`, `owned_files` (set to this task's test directory, e.g. `<AppName>Tests/Tasks/<task_id>/`), and `source_files` (the developer task's graph `owned_files`, i.e. the paired source paths the test agent should read to understand what was built). When the wave reports: the orchestrator runs `xcodegen generate` + `xcodebuild build-for-testing` once, then each task's tests run concurrently via `xcodebuild test-without-building -only-testing:<TargetName/ClassName> -destination id=<own UDID>` — each `-only-testing:` entry comes from that write agent's reported `test_classes` list. Scope-check attribution during test_engineer waves uses the assigned test directories (`owned_files` per task), not the graph's source `owned_files`; `project.yml` changes are attributable only to the registration pre-step dispatch.
- Test failures route back to the owning agents (with their failure output) for fix rounds, mirroring the developer wave-build loop (≤3 rounds, then `failed` → checkpoint). Fixes to test files re-enter `build-for-testing` serially.

## New app
(target path doesn't exist, or exists but has no `.ios-orchestrator/state.json`, and is otherwise empty/non-project)

If `target_project_path` exists, is non-empty, and contains no recognizable Xcode/SPM project (i.e. doesn't match "Existing non-orchestrator project" below), confirm with the user via `AskUserQuestion` before proceeding as `new_app` - the directory may contain unrelated files that the Developer's scaffolding could conflict with.

1. **architect**: dispatch `ios-architect` with `mode: new_app`, `target_project_path`, `interview_output`. It writes `docs/architecture.md`, reports `screens_affected`, and returns the task graph — validate and persist it per "Task graph and waves" above before the checkpoint (which renders the graph and `ui_impact` flags for user correction — see `checkpoints.md`). Checkpoint.
2. **ui_designer**: if `screens_affected: true`, ask the design-mode question (`design-mode.md`) if not yet answered, then dispatch `ios-ui-designer` with `target_project_path`, `architecture_summary` (contents of `docs/architecture.md`), `design_mode`, `design_sources`. On a solo dispatch (single-task graph) it writes `docs/design.md`; fan-out dispatches instead *return* design sections that the orchestrator assembles into `docs/design.md` (see the ui_designer mechanics above). Checkpoint. If `screens_affected: false`, skip to step 3.
3. **developer (implement)**: first check `which xcodegen` - if not installed, tell the user: "The `new_app` scaffold requires xcodegen. Install it with `brew install xcodegen`, then re-run `/ios-genesis <path>` to resume from this point." and stop (`state.json` still shows the prior phase as complete, so resuming re-enters here; this mirrors `pr-review-flow.md`'s `gh auth status` check). Then dispatch `ios-developer` with `dispatch_type: implement`, `mode: new_app`, `target_project_path`, `architecture_summary`, `design_summary` (if step 2 ran). On a solo dispatch (single-task graph) it scaffolds an xcodegen project and builds until it compiles; on a multi-task graph, follow the developer mechanics above — foundation solo (it scaffolds and builds itself), then screen/feature waves (write-only, wave-end integration builds), then integration solo. Checkpoint.
4. **visual_verification**: only if `screens_affected: true` (otherwise skip to the next phase) - run the visual verification loop (see below), then checkpoint.
5. **test_engineer**: dispatch `ios-test-engineer` with `dispatch_type: test`, `mode: new_app`, `target_project_path`, `architecture_summary`, `design_summary` (if applicable), `developer_summary` (from step 3's report). On a solo dispatch (single-task graph) it writes tests and runs them until passing; multi-task graphs follow the test_engineer mechanics above (serial registration pre-step, write-only waves, one `build-for-testing`, parallel `test-without-building`). Checkpoint.
6. **pr_creation**: see `pr-review-flow.md` (`branch_name: "feature/initial-implementation"`, including the no-GitHub-remote checkpoint if needed). The working branch already exists from initialization, so this phase is slimmed to remote setup, push, and PR opening. Checkpoint.
7. **code_review**: see `pr-review-flow.md`'s review loop. Checkpoint.
8. **merge**: see `pr-review-flow.md`. Checkpoint.
9. **release_manager**: dispatch `ios-release-manager` with `target_project_path`, `architecture_summary`, `design_summary` (if applicable). It writes `docs/release-checklist.md`. Checkpoint. (This is the final phase - after this checkpoint, the run is complete.)

## Feature addition
(`.ios-orchestrator/state.json` exists, OR the project exists with no state file - see "Existing non-orchestrator project" below)

1. **architect**: dispatch `ios-architect` with `mode: feature_addition`, `target_project_path`, `interview_output`. It does a codebase survey and returns a scope summary (no file written) plus `screens_affected` and the task graph — validate and persist the graph per "Task graph and waves" above before the checkpoint. Checkpoint persists the scope summary as `architecture_summary` in `state.json` (see `checkpoints.md`), since no file is written and the Architect has no memory.
2. **ui_designer**: only if `screens_affected: true` - same as new app step 2 (including the solo-writes / fan-out-returns split), but `architecture_summary` is `state.json`'s persisted scope summary text (not a file). Otherwise skip to step 3.
3. **developer (implement)**: dispatch `ios-developer` with `dispatch_type: implement`, `mode: feature_addition`, `target_project_path`, `architecture_summary` (scope summary text), `design_summary` (if step 2 ran) — solo dispatch on single-task graphs, otherwise per the developer mechanics above. Checkpoint.
4. **visual_verification**: only if `screens_affected: true` - same as new app step 4.
5. **test_engineer**: same as new app step 5 (including the solo/fan-out split), with `mode: feature_addition`. Checkpoint.
6. **pr_creation**: see `pr-review-flow.md` (`branch_name: "feature/<slug>"`, slug derived from the change description). The working branch already exists from initialization, so this phase is slimmed to remote setup, push, and PR opening. Checkpoint.
7. **code_review**: see `pr-review-flow.md`'s review loop. Checkpoint.
8. **merge**: see `pr-review-flow.md`. Checkpoint.
9. **release_manager**: skipped unless the user explicitly requests a release-readiness pass (if requested, dispatch as in new app step 9). This is the final phase either way - after step 8's checkpoint (or step 9's, if run), the run is complete.

## Visual verification loop

Runs inside the `visual_verification` phase (both modes, only when `screens_affected: true`). Placement before `test_engineer` means tests are written against final, visually-verified code. Capped at 2 rounds, mirroring the `code_review` loop. On multi-task graphs the loop runs **per projected task** (verifiers dispatched in waves per the visual_verification mechanics above, round counter in that task's `results.verification_round`); on single-task graphs it runs once, with the top-level `verification_round` (see `state-schema.md`'s dual-mode rule).

Dispatch inputs for `ios-visual-verifier`: `mode`, `target_project_path`, `design_mode`, `design_summary`, `design_reference` (single-task graphs: the Figma file link for `figma`, `design_sources` for `bring_your_own`, `"none"` otherwise; fan-out dispatches: the task's `results.design_reference`), and the verification round. Single-task/solo dispatches additionally get `app_scheme` (the Developer's reported `app_scheme` for `new_app` — on resume, `project.yml`'s `name:` — or `"discover"` for `feature_addition`) and NO `task_id` — the verifier self-selects its simulator and builds itself. Fan-out dispatches additionally get `task_id` (its presence is the verifier's mode discriminator — never include it in a single-task dispatch), `simulator_udid` (the device allocated to this verifier — see the visual_verification mechanics above), `bundle_id` (the app's bundle identifier, read from `xcodebuild -showBuildSettings` as `PRODUCT_BUNDLE_IDENTIFIER` at the orchestrator's pre-install build step), and `screen_name` (the task's primary screen name as registered in the router registry — screens register under their `docs/design.md` screen names; for a task spanning several screens, use the task's first-listed screen and list the remaining screens in that verifier's `unverified`/risks as usual).

1. Capture the scope-check baseline per `role-boundaries.md` (the repo and working branch exist from initialization in both modes; the method depends on whether the phase fans out). Set the verification round to 1. Dispatch `ios-visual-verifier`.
2. `status: pass` → the loop concludes for this task.
3. `status: skipped` → append an `open_risks` entry with the skip reason; the loop concludes for this task. (Do not loop.)
4. `status: issues_found`:
   a. Dispatch `ios-developer` with `dispatch_type: address_visual`, plus its always-required fields (`mode`, `target_project_path`, `architecture_summary`, `design_summary`), `verifier_findings` (verbatim), `screenshot_paths` (from the verifier report's `screenshots` field), and `work_summary` (from `phases_completed`). If the developer reports a build failure after its 3 attempts, stop looping and surface the failure at the checkpoint - the user decides. (If several tasks' fixes land concurrently, the wave-end integration-build rule applies instead of per-agent builds — see the visual_verification mechanics above.)
   b. If the verification round `== 1`: once the fix builds successfully, run `simctl install <udid> <path-to-rebuilt-.app>` on each affected task's allocated UDID before re-dispatching those verifiers — round 2 must screenshot the fixed binary, not the round-1 install. Then increment to 2, re-dispatch the verifier with `previous_findings` (the round-1 findings), and go to step 2.
   c. If the verification round `== 2` and findings remain: stop looping. Append the unresolved findings as `open_risks` entries and surface them at the checkpoint - the user decides (Continue / Make changes first / Stop).
5. The checkpoint runs once, after the loop concludes for every projected task (like `code_review`): `phase_status: "complete"` either way, round counters persisted as set by the loop.

## Existing non-orchestrator project

If `target_project_path` exists, contains an Xcode/SPM project, but has no `.ios-orchestrator/state.json`: treat as `feature_addition`, first run. After the orchestrator interview (step 0), initialize `state.json` (per `state-schema.md`'s Initialization section) before dispatching the Architect, and instruct the Architect (in its dispatch prompt) to do a quick codebase survey (it does this automatically per `agents/ios-architect.md`). Initialization includes the git-model edge cases: if the current checkout is on a non-default branch, or the working tree is dirty, ask the user at the interview checkpoint (branch base / commit-stash-proceed) before proceeding — see `state-schema.md`.

## Resuming

See `state-schema.md`'s Resuming section for the drift-detection procedure (including the mid-wave rule: tasks recorded `in_progress` reset to `pending` and re-dispatch fresh). Rebuild the task board from `state.json` per `task-board.md`'s "On resume" section. Once resumed, continue the sequence above from the recorded `phase`/`phase_status`.
