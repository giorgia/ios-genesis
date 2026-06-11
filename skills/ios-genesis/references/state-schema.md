# State File Schema

`<target-project-path>/.ios-orchestrator/state.json` is written and updated by the orchestrator (not subagents) after each phase completes. It enables resuming a run later and tracks cumulative risks/blockers.

## Schema

```json
{
  "mode": "new_app",
  "phase": "code_review",
  "phase_status": "in_progress",
  "review_round": 1,
  "screens_affected": true,
  "design_mode": "text",
  "design_sources": [],
  "last_commit_sha": "a1b2c3d4...",
  "pr_url": "https://github.com/user/repo/pull/1",
  "open_risks": [
    {
      "id": "risk-1",
      "phase": "developer",
      "raised_at": "2026-06-11T10:45:00Z",
      "description": "No push notification API key found - feature stubbed out pending credentials."
    }
  ],
  "phases_completed": [
    {
      "phase": "architect",
      "completed_at": "2026-06-11T10:00:00Z",
      "summary": "3 modules: Networking, Persistence, UI. Single-target SwiftUI app.",
      "artifact": "docs/architecture.md"
    }
  ]
}
```

## Field reference

- `mode`: `"new_app"` or `"feature_addition"`. Set once, at initialization, based on whether `.ios-orchestrator/state.json` existed at the start of the run.
- `phase`: one of `architect`, `ui_designer`, `developer`, `test_engineer`, `pr_creation`, `code_review`, `merge`, `release_manager` — the phase currently in progress or last completed.
- `phase_status`: `"in_progress"` or `"complete"`.
- `review_round`: current round of the PR review loop (see `pr-review-flow.md`). Monotonically increasing across the PR's lifecycle: `0` before the first review dispatch, `1` for the first review, `2` for the second (the loop is capped at 2 rounds — see `pr-review-flow.md`).
- `screens_affected`: `true`, `false`, or `null` if not yet determined (set by the Architect's report). Determines whether `ui_designer` runs and whether the design-mode question is asked (see `design-mode.md`).
- `design_mode`: `"text"`, `"figma"`, `"claude_design"`, or `"bring_your_own"`. Only meaningful when `screens_affected: true`; otherwise unset (key omitted).
- `design_sources`: list of file paths/URLs to user-provided designs. Only populated when `design_mode` is `"bring_your_own"`; empty otherwise.
- `last_commit_sha`: HEAD of the project's default branch as of the last orchestrator update. Used for drift detection on resume, and updated after the `developer`/`pr_creation` phases (see `role-boundaries.md` for which phases commit).
- `pr_url`: set once `pr_creation` completes; used by `code_review` and `merge`. Unset (key omitted) before then.

Throughout this schema, "unset" means the key is omitted from the JSON entirely (not present with a `null` value), except for `screens_affected`, which is explicitly `null` while undetermined since the orchestrator needs to distinguish "not yet known" from "known to be false."
- `open_risks`: list of risks/blockers raised by subagents that haven't been resolved or dismissed. Each entry has:
  - `id`: stable identifier (`risk-1`, `risk-2`, ... incrementing across the whole run)
  - `phase`: the phase that raised it (same short names as the `phase` field)
  - `raised_at`: ISO-8601 timestamp
  - `description`: human-readable description
  - Removal: only via (a) the user dismissing/resolving it by `id` at a checkpoint, or (b) a later subagent's report explicitly referencing the `id` as resolved by its work. Never silently dropped.
- `phases_completed`: append-only history. Each entry has `phase`, `completed_at`, `summary` (from the subagent's report), and `artifact` (file path, or `"none"` if the phase produced no file — e.g. `feature_addition` architect, or `code_review`/`merge`).

## Initialization

For a brand-new run (`mode: new_app`, or `feature_addition` against a project with no existing state file), the orchestrator creates `.ios-orchestrator/state.json` with: `mode` set appropriately, `phase: "architect"`, `phase_status: "in_progress"`, `review_round: 0`, `screens_affected: null` (unknown until the Architect reports), `design_mode`/`design_sources` unset, `last_commit_sha` set to the current `git rev-parse HEAD` of the target project (or omitted if the project doesn't exist yet / has no commits), `pr_url` unset, `open_risks: []`, `phases_completed: []`.

## Resuming

On invocation, if `.ios-orchestrator/state.json` exists, the orchestrator reads it to determine where to pick up. Before continuing, it runs `git rev-parse HEAD` on the project's default branch and compares it to `last_commit_sha`:

- **Match**: proceed from `phase`/`phase_status` as recorded (if `phase_status: "complete"`, advance to the next phase in sequence; if `"in_progress"`, re-dispatch that phase).
- **Mismatch**: flag the drift to the user — show `last_commit_sha`, the current HEAD, and a one-line `git log` of the commits in between — and ask via `AskUserQuestion` whether to: proceed anyway (treating the new commits as part of this run's work), re-run the current phase from scratch, or have the Architect re-scope first (jumps back to the `architect` phase).
