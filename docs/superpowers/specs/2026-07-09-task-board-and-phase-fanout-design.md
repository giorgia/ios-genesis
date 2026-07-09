# ios-genesis v0.3.0 — Live Task Board and Phase Fan-Out

**Date:** 2026-07-09
**Status:** Approved by Giorgia (brainstorming session, 2026-07-09); revised after spec review rounds 1–2
**Builds on:** v0.2.0 (xcodegen scaffold + visual verification, merged at `45e2680`)

## Problem

Two limitations surfaced during the v0.2.0 validation runs:

1. **Opacity.** During a run, the user sees a stream of tool-call output. There is no at-a-glance view of which agent is running, what it is working on, or how much of the pipeline remains.
2. **Serialism.** The pipeline is strictly sequential even when the work is embarrassingly parallel. A design with many screens or a request with multiple features runs one specialist at a time; a team of seven agents works single-file.

v0.3.0 addresses both with one mechanism: a task graph that the orchestrator both **executes in parallel waves** and **renders live** on Claude Code's native task board.

## Decisions made during brainstorming

| Decision | Choice |
|---|---|
| Parallel unit | **Phase fan-out**: phases and their checkpoints stay sequential; within a phase, N agents run concurrently on decomposed tasks |
| Code-conflict strategy | **File ownership + dependency edges**: exclusive `owned_files` per task, shared code isolated into a foundation task that blocks the rest |
| Partial failure | **Finish the wave, surface at checkpoint**: siblings run to completion; the checkpoint shows per-task outcomes and the user chooses retry / drop / stop |
| Concurrency | **Default cap 3**, announced with the wave plan at the preceding checkpoint, overridable per run |

**Design principle added in review round 2:** in a single shared Xcode target, *compilation is inherently an integration act* — a build sweeps in every file present, including siblings' work-in-progress. v0.3.0 therefore parallelizes **writing**, and treats **building as a serial, orchestrator-run integration step** at wave end. No agent builds concurrently with another agent's unfinished code.

## 1. Task graph (state.json)

The Architect **returns** the graph in its report; the orchestrator validates and persists it — the orchestrator remains `state.json`'s only writer, per `state-schema.md`'s existing rule. Validation checks: ownership disjointness (below) and that `depends_on` forms a DAG (a cycle would deadlock the wave scheduler). On failure, re-dispatch the Architect with the defect named, at most twice, then surface to the user at the checkpoint.

New `state.json` field, fully documented in `state-schema.md` for both modes (the v0.2.0 validation's finding #5 was an undocumented field causing divergent behavior between runs):

```json
"task_graph": {
  "cap": 3,
  "tasks": [
    {
      "id": "T1",
      "title": "Foundation: shared models, app entry, theme, debug screen router",
      "kind": "foundation",
      "owned_files": ["App/Models/", "App/TipTopApp.swift", "App/Theme/", "App/Debug/"],
      "depends_on": [],
      "ui_impact": false,
      "status": "pending",
      "results": {}
    },
    {
      "id": "T2",
      "title": "Onboarding screen",
      "kind": "screen",
      "owned_files": ["App/Views/Onboarding/"],
      "depends_on": ["T1"],
      "ui_impact": true,
      "status": "pending",
      "results": {}
    },
    {
      "id": "T9",
      "title": "Integration: navigation wiring + screen-router registry",
      "kind": "integration",
      "owned_files": ["App/Navigation/", "App/Debug/ScreenRegistry.swift"],
      "depends_on": ["T2", "..."],
      "ui_impact": false,
      "status": "pending",
      "results": {}
    }
  ]
}
```

- `kind`: `foundation` | `screen` | `feature` | `integration`.
  - **foundation** (0 or 1): shared models, app entry, theme/design-system, and (when verifier work exists — see §3) the debug screen-router mechanism. Blocks every task that reads shared surfaces.
  - **integration** (0 or 1): navigation wiring and the router *registry* entries — the shared files that must reference every screen view and therefore cannot exist before the screens do. Depends on all `screen`/`feature` tasks; runs solo as the final developer wave.
  - **screen** / **feature**: the parallel work units.
- `ui_impact` (boolean): drives per-phase participation (§3). `screen` tasks are always `true`; `feature` tasks set it when they change anything user-visible (the Architect decides; the post-architect checkpoint shows the flags so the user can correct them — this keeps a visual fix like TipTop's clipped chip inside the visual-verification guarantee).
- `owned_files`: exclusive set of **literal directory prefixes** (or single file paths). Disjointness rule, cheap and decidable: no owned path may be a path-prefix of another task's owned path.
- `status`: `pending` | `in_progress` | `complete` | `failed` | `dropped`. `results` accumulates per-phase outcomes (`design_status`, `build_status`, `verify_status` + `verification_round`, `tests_status`, per-task `design_reference` for figma mode) as the task flows through phases.
- **Small scopes:** a single-task graph (one `feature` task, no foundation/integration). Execution degenerates to the v0.2.0 sequential flow, and the v0.2.0 top-level fields (`verification_round`, etc.) keep their existing meaning. **Multi-task graphs** move round counters into each task's `results`; `state-schema.md` documents both forms side by side. **Back-compat:** a `state.json` with no `task_graph` (any pre-0.3.0 run) resumes with the sequential flow unchanged.

### Git model (change to the v0.2.0 flow)

v0.2.0 had no git repository until `pr_creation` (`new_app`), which made scope checks impossible pre-PR and would make wave attribution impossible. v0.3.0 unifies both modes:

- **At state initialization** (post-interview, so the feature slug is known): `git init` if no repo (new_app) — with an immediate **first act in both modes** of ensuring `.gitignore` contains `.ios-orchestrator/` (create the file for new_app — this replaces the feature_addition-only carve-out and prevents state/screenshots from ever being tracked); then an initial commit on the default branch if the repo is empty; then **create and switch to the working branch** (`feature/initial-implementation` or `feature/<slug>`).
- **All run commits land on the working branch**: the orchestrator commits at each post-phase checkpoint (`wip(<phase>): <one-liner>`) and at each wave-build round inside fanned-out phases (`wip(<phase>/wave-N)`). The default branch receives nothing until `merge` squash-merges the PR — no orphaned wip commits on main.
- **`pr_creation` slims down**: branch creation and `git init` move out (already done at init); it keeps remote setup (including the new_app "create a GitHub repo?" question), push, and PR opening.
- **`last_commit_sha`** is now updated at every orchestrator commit; the resume drift check compares `git rev-parse HEAD` against it exactly as today, and `state-schema.md`'s description is updated accordingly.
- **Edges:** the working branch is based on the default branch (feature_addition: if the user's checkout is on another branch, ask at the interview checkpoint before proceeding); if `feature/<slug>` already exists, suffix `-2`. A dirty working tree at feature_addition init also gets asked about (commit/stash/proceed) — the always-commit model would otherwise sweep the user's uncommitted changes into wip commits. **Pre-0.3.0 back-compat includes the git model:** a resumed pre-0.3.0 state file keeps the legacy flow end-to-end — including `pr_creation`'s old `git init` responsibility for a mid-pipeline `new_app` resume that has no repo yet.

## 2. Visual layer: native task board

The orchestrator drives Claude Code's built-in task tools — no custom rendering:

- At graph acceptance, `TaskCreate` one board entry per pipeline task; `TaskUpdate` with `addBlockedBy` mirrors `depends_on`.
- On dispatch: `status: in_progress`, `activeForm` naming the agent and work ("ios-developer #2 · building Settings screen"). On report: `completed`, or kept `in_progress` with the failure noted in the subject until the checkpoint resolves it (retry/drop/stop → re-dispatch/`deleted`/left as-is).
- **Sequential runs are visual too:** when the graph is single-task, the orchestrator instead creates one board entry per *phase* (architect → … → merge), so every run gets the live view.
- The board is presentation only. `state.json` remains the single source of truth. If task tools are unavailable (non-Claude-Code host), skip board calls — execution is unaffected.

## 3. Fan-out mechanics per phase

Phases run in their existing order; fan-out happens inside a phase.

**Phase projection.** Each phase computes its working set from the graph (table below). `depends_on` edges are evaluated **within the projection**: a dependency with no work in the current phase counts as satisfied. Waves = unblocked tasks in the projection, at most `cap` at a time, dispatched as concurrent subagents.

| Phase | Works on |
|---|---|
| ui_designer | tasks with `ui_impact: true` |
| developer | all tasks (foundation solo → screens/features in waves → integration solo) |
| visual_verification | tasks with `ui_impact: true` |
| test_engineer | registration pre-step, then `foundation` + `screen` + `feature` tasks (foundation's models get dedicated tests) |
| pr_creation / code_review / merge / release_manager | whole-run (no fan-out, unchanged) |

### ui_designer
One agent per `ui_impact` task. Each **returns its design section in its report**; the orchestrator assembles `docs/design.md` (single writer). In `figma` mode each task's mockup is its own Figma file; the link is stored in that task's `results.design_reference` and passed to that task's verifier (the assembled `docs/design.md` lists per-screen Figma links instead of one). `claude_design`: per-task paste summaries, concatenated by the orchestrator into one user handoff at the checkpoint. `bring_your_own`: the Architect maps each entry in `design_sources` to a task at graph creation; a task's mapped sources become its `results.design_reference`.

### developer — write in parallel, build as integration
- Same checkout, exclusive ownership: the dispatch prompt includes the task's `owned_files`; edits outside them are forbidden (foundation outputs are read-only context). **Fan-out wave agents do not build** — they write code (using `swiftc -typecheck <own files>` for a best-effort local sanity pass at most).
- **Wave-end integration build (orchestrator, serial):** when all wave agents report, run `xcodegen generate` once, then `xcodebuild build` once. This is the only regeneration and the only build — no shared-`.xcodeproj` write race, no compiling of sibling WIP mid-task, no DerivedData contention (per-task `derivedDataPath` is dropped; it solved the wrong problem).
- **Build-failure routing:** compile errors are attributed to tasks by file ownership and the owning agents re-dispatched with their errors (concurrently, if several tasks failed). Up to 3 wave-build rounds; still-failing tasks are marked `failed` and surface at the checkpoint per the failure policy. Errors in files no task owns → surfaced at the checkpoint as an integration defect.
- On wave-build success: `wip(developer/wave-N)` commit; attribution/scope check via `git diff --name-only <previous wip commit>` mapped to owned-path prefixes; unattributable paths flagged at the checkpoint.
- Solo waves (foundation, integration, and every single-task graph) keep the v0.2.0 agent behavior: the agent builds itself, up to 3 attempts.
- `project.yml` edits are reserved to `foundation`/`integration` tasks by construction (glob `sources` make screen/feature file additions invisible to it).

### visual_verification
- Code is frozen by this phase, so the orchestrator **builds once** and `simctl install`s the same `.app` onto one simulator per verifier task (own UDID, allocated from `simctl list devices available`; fewer devices than cap → smaller waves, a rule that applies equally to test_engineer's parallel `test-without-building` runs). Verifiers lose their build step in fan-out mode (they launch, screenshot, compare); the single-task/sequential path keeps v0.2.0 behavior. `ios-visual-verifier.md` switches from `booted` to explicit-UDID targeting.
- **Screen reachability:** the foundation task adds the debug-only router *mechanism* (`-ios-genesis-screen <Name>`, `#if DEBUG`); the integration task adds the *registry* entries once screens exist. Verifiers launch via `simctl launch <udid> <bundle> -ios-genesis-screen <Name>`. For `feature_addition`: the router ships inside the integration task only when the graph has verifier work; if the app lacks it and the graph has no integration task, verification falls back to root-screen-only + an `open_risks` entry naming the gap (never a hard failure).
- Screenshots move to per-task subdirectories: `.ios-orchestrator/screenshots/<task-id>/round-<N>-<screen>.png` (part of the `ios-visual-verifier.md` edit).
- Per-task loop keeps v0.2.0 semantics (2 rounds, `address_visual` re-dispatch); `address_visual` fixes re-enter the integration-build rule if multiple fixes land concurrently (in practice fixes are per-task and serialized by the loop).

### test_engineer
- **Registration pre-step (serial, once):** if test targets are missing, a single dispatch registers them in `project.yml` + `xcodegen generate` — the one sanctioned shared-file edit, with no siblings running.
- **Write in parallel, build once, run in parallel:** agents write test files into per-task directories without running them. When the wave reports: orchestrator runs `xcodegen generate` + `xcodebuild build-for-testing` once, then each task's tests run concurrently via `xcodebuild test-without-building -only-testing:<task's test classes> -destination id=<own UDID>`. Test failures route back to owning agents (with their failure output) for fix rounds, mirroring the developer wave-build loop (≤3 rounds; fixes to *test* files re-enter build-for-testing serially).

## 4. Checkpoints

**Invariant: one user gate per phase — the post-phase checkpoint.** No separate pre-fan-out gate; each post-phase checkpoint *previews the next phase's wave plan* (projection, dependencies, cap, wave count — "developer: 8 tasks, cap 3 → foundation, then 3+3+1, then integration") alongside the usual summary. Options gain cap control: Continue / Continue with different cap / Make changes first / Stop. The post-architect checkpoint is where the whole graph — including `ui_impact` flags — gets user eyes.

- **Post-phase results:** per-task table (✓ / ✗ / skipped, one line each), then the standard checkpoint content. Failures: siblings always run to completion; per failed task the user chooses **retry** (re-dispatch with sibling summaries as context), **drop** (append `open_risks`, `status: dropped`), or **stop**.
- **Checkpoint commits and scope-check ordering:** the `wip(<phase>)` commit is the **last act** of the checkpoint, after the scope check has run — against the still-uncommitted working tree (`git status --porcelain`, sequential phases) or against `git diff --name-only <previous wip commit>` (fanned-out phases). Committing first would blind the porcelain-based checks. This reworks `role-boundaries.md`'s "How to check" for **every** phase (its methods were premised on the dead "no repo until pr_creation" model); the wip commit is skipped when there is nothing to commit (`code_review`, `merge`, clean verification passes). Post-`merge` phases (`release_manager`) commit to the default branch — "run commits land on the working branch" applies *until* merge.
- **Drop semantics (defined):** dropping a failed task (a) **reverts its `owned_files` to the last wip commit** (checkout for tracked paths, delete untracked ones) so no non-compiling code survives into later integration builds; (b) **excludes the task from all subsequent phase projections**; (c) dependents treat the dropped dependency as satisfied (the integration task simply doesn't wire it); (d) appends the `open_risks` entry. A phase's `wip(<phase>)` commit happens only once every failed task in the phase is resolved (retried to success or dropped-and-reverted) — wip commits are always buildable.
- **Failure path and the one-gate invariant:** when a task exhausts its wave-build rounds, the phase concludes early (dependents like the integration task not yet run) and the checkpoint fires; retry/drop re-enters the wave scheduler, so the developer checkpoint can legitimately fire again after the remaining waves complete. The "one gate per phase" invariant reads per *pass*, not per calendar phase.
- **Structural-drop warning:** when a dropped task still has dependents in later projections (dropping `foundation` orphans everything; dropping `integration` ships unwired screens), the checkpoint says so explicitly before accepting the drop.
- **Resume mid-wave:** tasks recorded `in_progress` reset to `pending` and re-dispatch fresh; the dispatched agent is instructed to first inspect its `owned_files` for partial prior work. Completed tasks are never re-run.

## 5. Affected documents

Implementation planning should expect edits to: `state-schema.md` (task_graph, dual-mode round counters, git model: init-time repo/branch/ignore, `last_commit_sha` update-per-commit rule), `orchestration-flow.md` (projections, waves, integration task, router, wave-build loops), `checkpoints.md` (wave preview, per-task results, failure options, **wip-commit responsibility**), `role-boundaries.md` (**full "How to check" rework for every phase** — diff-vs-wip-commit methods replace the no-repo-era assumptions, plus ownership attribution for fanned-out phases), `pr-review-flow.md` (git init + branch creation move out; remote/PR remain; legacy path retained for pre-0.3.0 resumes), `design-mode.md` (per-task Figma files/`design_reference` in fan-out replaces the single-link `design_mode_extra` flow), `ios-architect.md` (graph in report, ui_impact), `ios-ui-designer.md` (report-only design sections; per-task Figma files), `ios-developer.md` (ownership, no-build fan-out dispatches, integration dispatch), `ios-visual-verifier.md` (UDID targeting, no-build fan-out mode, router launch, per-task screenshot dirs), `ios-test-engineer.md` (registration pre-step, write-only fan-out dispatches, test-without-building), `SKILL.md` (board protocol).

## 6. Deferred (explicitly out of scope)

- **Worktree-per-task isolation** — merge machinery unjustified while ownership + integration builds hold.
- **Cross-phase pipelining** (starting a screen's developer task while sibling designs render) — revisit only if wave latency hurts.
- **Per-agent model selection** (fan-out on a cheaper model) — revisit if the cap-3 token bill stings.

## Validation plan

Same watcher protocol as v0.2.0 (user drives, watcher independently re-verifies claims against filesystem/GitHub/simulator):

1. **new_app, 3-screen app** — exercises foundation task, init-time git model (working branch, ignore-first commit ordering), wave writes + integration builds with failure routing, router + integration wiring, verifier fan-out on per-UDID simulators, wave cap.
2. **feature_addition, two parallel features on TipTop** — one of them the clipped-Custom-chip fix flagged `ui_impact: true` (closing the v0.2.0 validation's finding #3 loop and proving `feature` tasks keep the visual-verification guarantee).
3. **Failure + resume drills** — force one task's build failure (verify wave-build routing + checkpoint options); interrupt mid-wave and resume (verify pending-reset re-dispatch).

Blog post 7 (byline Fable) covers the build once validated.
