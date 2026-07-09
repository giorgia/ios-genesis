# ios-genesis v0.3.0 — Live Task Board and Phase Fan-Out

**Date:** 2026-07-09
**Status:** Approved by Giorgia (brainstorming session, 2026-07-09)
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
| Concurrency | **Default cap 3**, announced with the wave plan at the pre-fan-out checkpoint, overridable per run |

## 1. Task graph (state.json)

The Architect's report gains a task decomposition. New `state.json` field, fully documented in `state-schema.md` (every field, both modes — the v0.2.0 validation's finding #5 was an undocumented field causing divergent behavior between runs):

```json
"task_graph": {
  "cap": 3,
  "tasks": [
    {
      "id": "T1",
      "title": "Foundation: shared models, app entry, theme",
      "kind": "foundation",
      "owned_files": ["App/Models/**", "App/<AppName>App.swift", "App/Theme/**"],
      "depends_on": [],
      "status": "pending",
      "results": {}
    },
    {
      "id": "T2",
      "title": "Onboarding screen",
      "kind": "screen",
      "owned_files": ["App/Views/Onboarding/**"],
      "depends_on": ["T1"],
      "status": "pending",
      "results": {}
    }
  ]
}
```

- `kind`: `foundation` | `screen` | `feature`. Exactly one foundation task when shared code exists; it blocks all tasks that touch shared surfaces.
- `owned_files`: exclusive glob set. Two tasks' globs must not overlap; the Architect is responsible for disjointness, and the orchestrator validates it before accepting the graph (overlap → re-dispatch the Architect with the conflict named).
- `status`: `pending` | `in_progress` | `complete` | `failed` | `dropped`. `results` accumulates per-phase outcomes (`design_section_done`, `build_status`, `verify_status`, `tests_status`) as the task flows through phases.
- **Small scopes:** a single-task graph (one `feature` task, no foundation). Execution then degenerates to exactly the v0.2.0 sequential flow. **Back-compat:** a `state.json` with no `task_graph` (any pre-0.3.0 run) resumes with the sequential flow unchanged.

## 2. Visual layer: native task board

The orchestrator drives Claude Code's built-in task tools — no custom rendering:

- At graph acceptance, `TaskCreate` one board entry per pipeline task; `TaskUpdate` with `addBlockedBy` mirrors `depends_on`.
- On dispatch: `status: in_progress`, `activeForm` naming the agent and work ("ios-developer #2 · building Settings screen"). On report: `completed` (or kept `in_progress` with a failure note in the subject until the checkpoint resolves it).
- **Sequential runs are visual too:** when the graph is single-task, the orchestrator instead creates one board entry per *phase* (architect → … → merge), so every run gets the live view.
- The board is presentation only. `state.json` remains the single source of truth; the orchestrator is its only writer. If task tools are unavailable (non-Claude-Code host), skip board calls — execution is unaffected.

## 3. Fan-out mechanics per phase

Phases run in their existing order; fan-out happens inside a phase. Waves are computed from `depends_on` + cap: all unblocked tasks, at most `cap` at a time, dispatched as concurrent subagents.

### ui_designer
One agent per `screen` task. Each returns its design section **in its report**; the orchestrator assembles `docs/design.md` (single writer — designers never touch the shared file). Design-mode extras (Figma, etc.) remain per-screen within the agent.

### developer
- Same checkout, exclusive ownership. The dispatch prompt includes the task's `owned_files` and the instruction that edits outside them are forbidden (the foundation task's outputs are read-only context).
- Each concurrent agent builds with its own `-derivedDataPath .ios-orchestrator/derived/<task-id>` — concurrent xcodebuild against shared DerivedData is flaky. These paths live under `.ios-orchestrator/`, already gitignored.
- Post-wave scope check: attribute the wave's diff (`git status --porcelain` against the wave baseline) to tasks by ownership globs. Unattributable paths → flag at the checkpoint (same treatment as today's out-of-pattern changes). The init-time `.gitignore` append carve-out is unchanged.
- `project.yml` uses directory-glob `sources`, so parallel file additions never touch it; if a task genuinely needs a `project.yml` change (new target, new setting), that belongs to the foundation task by construction.

### visual_verification
- One verifier per `screen` task, each on its **own simulator UDID** (allocated by the orchestrator from `simctl list devices available`; fewer devices than cap → smaller waves for this phase).
- **Screen reachability:** the foundation task adds a debug-only launch-argument router — `-ios-genesis-screen <ScreenName>` presents that screen directly (compiled out of release builds via `#if DEBUG`). Verifiers pass it via `simctl launch`. A screen the router can't reach is verified at the root screen only, with an `open_risks` entry naming the gap. This router is the only new app-side mechanism in the release.
- The per-screen loop keeps v0.2.0 semantics (2 rounds, `address_visual` re-dispatch); `verification_round` moves into the task's `results`.

### test_engineer
Parallel per `feature`/`screen` task with the same ownership rules; test files live in per-task directories. Test *runs* are serialized per simulator (test execution is the contended resource, not test writing).

### pr_creation / code_review / merge / release_manager
Unchanged — inherently serial, single-task phases.

## 4. Checkpoints

Still exactly one checkpoint per phase.

- **Pre-fan-out (once per parallel phase):** show the wave plan — task list, dependencies, cap, wave count ("8 tasks, cap 3 → 3 waves"). Options: Continue / change cap / Make changes / Stop.
- **Post-phase:** per-task results table (✓ / ✗ / skipped, one line each), then the standard checkpoint. For failures (per the brainstorming decision): siblings always run to completion; the checkpoint offers per failed task — **retry** (re-dispatch with sibling summaries as context), **drop** (append `open_risks`, `status: dropped`), or **stop**.
- **Resume mid-wave:** tasks recorded `in_progress` reset to `pending` and re-dispatch fresh; the dispatched agent is instructed to first inspect its `owned_files` for partial prior work. Completed tasks are never re-run.

## 5. Deferred (explicitly out of scope)

- **Worktree-per-task isolation** — merge machinery unjustified while ownership + generated pbxproj holds.
- **Cross-phase pipelining** (starting a screen's developer task while sibling designs render) — revisit only if wave latency hurts.
- **Per-agent model selection** (fan-out on a cheaper model) — revisit if the cap-3 token bill stings.

## Validation plan

Same watcher protocol as v0.2.0 (user drives, watcher independently re-verifies claims against filesystem/GitHub/simulator):

1. **new_app, 3-screen app** — exercises foundation task, designer/developer/verifier fan-out, the launch-arg router, per-task DerivedData, wave cap.
2. **feature_addition, two parallel features on TipTop** — one of them the clipped-Custom-chip fix (closing the v0.2.0 validation's finding #3 loop), exercising parallel tasks against an existing codebase.
3. **Failure + resume drills** — force one task's build failure (verify wave-completion + checkpoint options); interrupt mid-wave and resume (verify pending-reset re-dispatch).

Blog post 7 (byline Fable) covers the build once validated.
