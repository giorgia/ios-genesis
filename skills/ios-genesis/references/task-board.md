# Task Board

The orchestrator drives Claude Code's native task board for live visibility into pipeline progress. The board is **presentation only** — `state.json` remains the single source of truth. If the task tools (`TaskCreate`, `TaskUpdate`) are unavailable (non-Claude-Code host), skip all board calls; execution is unaffected.

## At graph acceptance

When the orchestrator validates and persists the Architect's graph:

- `TaskCreate` one board entry per pipeline task.
  - `subject`: the task's `title` from `task_graph.tasks`.
  - `description`: `kind` + `owned_files` + which phases this task participates in (e.g. `screen · App/Views/Home/ · ui_designer, developer, visual_verification`).
- `TaskUpdate` with `addBlockedBy` for each `depends_on` edge, mirroring the graph's dependency structure.

## Single-task graphs

When the graph contains exactly one task (sequential flow), the orchestrator instead `TaskCreate`s one board entry per **phase** in pipeline order (architect → ui_designer → developer → visual_verification → test_engineer → pr_creation → code_review → merge → release_manager), so every run gets the live view. Apply the same dispatch/report/failure rules below, keyed on phase rather than task.

## On dispatch

When an agent is dispatched for a task (or phase):

- `TaskUpdate status: in_progress`
- `TaskUpdate activeForm`: `"<agent-role> · <doing what>"` — name the agent and the specific work, e.g. `"ios-developer #2 · building Settings screen"` or `"ios-visual-verifier · verifying Onboarding screen"`.

For fan-out waves, update each concurrently dispatched task in the same step before waiting for reports.

## On report

When an agent returns its report:

- **Success:** `TaskUpdate status: completed`.
- **Failure:** leave `status: in_progress`; `TaskUpdate subject` to append the failure summary (e.g. `"Home screen [build failed: missing import]"`). The board reflects the unresolved state until the checkpoint resolves it:
  - **Retry:** clear the subject suffix and re-dispatch; the dispatch rule above re-applies.
  - **Drop:** `TaskUpdate status: deleted`.
  - **Stop:** leave as-is (the run ends; the board shows the failure for context).

## On resume

When resuming a run in a fresh session, rebuild the board from `state.json`:
- **Multi-task graphs:** `TaskCreate` one entry per task in `task_graph.tasks`; immediately `TaskUpdate status: completed` for `complete` tasks, skip `dropped` ones, then re-add `addBlockedBy` edges.
- **Single-task graphs:** `TaskCreate` one entry per phase; immediately `TaskUpdate status: completed` for already-completed phases.

## What the board does not replace

The board renders task state visually; it does not drive sequencing, failure routing, or phase projection. All of that logic runs against `task_graph.tasks` in `state.json`. See `state-schema.md` for field definitions (`kind`, `owned_files`, `depends_on`, `status`; `dropped` is a value of `status`) and `checkpoints.md` for failure-resolution semantics.
