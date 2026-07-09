# State File Schema

`<target-project-path>/.ios-orchestrator/state.json` is written and updated by the orchestrator (not subagents) after each phase completes. It enables resuming a run later and tracks cumulative risks/blockers.

## Schema

```json
{
  "mode": "new_app",
  "interview_output": "Build a single-screen counter app...",
  "phase": "code_review",
  "phase_status": "in_progress",
  "review_round": 1,
  "verification_round": 1,
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
- `interview_output`: the requirements/approach/design summary approved at the end of the orchestrator's Step 0 interview (see `orchestration-flow.md`). Set once, at initialization, before the Architect's first dispatch — this lets a resume re-dispatch the Architect with the same input if the run stopped before the Architect's checkpoint completed.
- `architecture_summary`: only present when `mode: "feature_addition"`. The Architect's full scope-summary text (it writes no file in this mode — see `agents/ios-architect.md`), persisted after the Architect's checkpoint so later phases (`ui_designer`, `developer`, `test_engineer`, `code_reviewer`) can use it without relying on the Architect's memory. For `mode: "new_app"`, this text lives in `docs/architecture.md` instead and this key is omitted.
- `phase`: one of `architect`, `ui_designer`, `developer`, `visual_verification`, `test_engineer`, `pr_creation`, `code_review`, `merge`, `release_manager` — the phase currently in progress or last completed.
- `phase_status`: `"in_progress"` or `"complete"`.
- `review_round`: current round of the PR review loop (see `pr-review-flow.md`). Monotonically increasing across the PR's lifecycle: `0` before the first review dispatch, `1` for the first review, `2` for the second (the loop is capped at 2 rounds — see `pr-review-flow.md`).
- `verification_round`: current round of the visual verification loop (see `orchestration-flow.md`). Monotonic, analogous to `review_round`: `0` before the first verifier dispatch, `1` for the first verification, `2` for the second (the loop is capped at 2 rounds). The phase's `phases_completed` artifact is `.ios-orchestrator/screenshots/` (or `"none"` if the phase was skipped).
- `screens_affected`: `true`, `false`, or `null` if not yet determined (set by the Architect's report). Determines whether `ui_designer` runs and whether the design-mode question is asked (see `design-mode.md`).
- `design_mode`: `"text"`, `"figma"`, `"claude_design"`, or `"bring_your_own"`. Only meaningful when `screens_affected: true`; otherwise unset (key omitted).
- `design_sources`: list of file paths/URLs to user-provided designs. Only populated when `design_mode` is `"bring_your_own"`; empty otherwise.
- `app_scheme`: the Xcode scheme used to build/launch the app. For `new_app`: set from the Developer's `implement` report (it matches `project.yml`'s `name:`, which remains the authoritative source on resume). For `feature_addition`: unset (key omitted) — the Visual Verifier is dispatched with `"discover"` and resolves the scheme itself via `xcodebuild -list`.
- `last_commit_sha`: HEAD of the project's git repository (whichever branch is currently checked out) as of the last orchestrator update - the default branch before `pr_creation`, the feature branch during `pr_creation`/`code_review`, and the default branch again after `merge`. Updated after the `pr_creation`, `code_review`, and `merge` phases (see `role-boundaries.md`/`checkpoints.md` for details). Unset (key omitted) for `new_app` before `pr_creation`'s `git init` creates the repo.
- `pr_url`: set once `pr_creation` completes; used by `code_review` and `merge`. Unset (key omitted) before then.
- `open_risks`: list of risks/blockers raised by subagents that haven't been resolved or dismissed. Each entry has:
  - `id`: stable identifier (`risk-1`, `risk-2`, ... incrementing across the whole run)
  - `phase`: the phase that raised it (same short names as the `phase` field)
  - `raised_at`: ISO-8601 timestamp
  - `description`: human-readable description
  - Removal: only via (a) the user dismissing/resolving it by `id` at a checkpoint, or (b) a later subagent's report explicitly referencing the `id` as resolved by its work. Never silently dropped.
- `phases_completed`: append-only history. Each entry has `phase`, `completed_at`, `summary` (from the subagent's report), and `artifact` (file path, or `"none"` if the phase produced no file — e.g. `feature_addition` architect, or `code_review`/`merge`).

Throughout this schema, "unset" means the key is omitted from the JSON entirely (not present with a `null` value), except for `screens_affected`, which is explicitly `null` while undetermined since the orchestrator needs to distinguish "not yet known" from "known to be false."

## Initialization

For a brand-new run (`mode: new_app`, or `feature_addition` against a project with no existing state file), the orchestrator creates `.ios-orchestrator/state.json` with: `mode` set appropriately, `interview_output` set from Step 0's interview result, `phase: "architect"`, `phase_status: "in_progress"`, `review_round: 0`, `verification_round: 0`, `screens_affected: null` (unknown until the Architect reports), `design_mode` unset, `design_sources: []`, `last_commit_sha` unset for `new_app` (no repo yet — created during `pr_creation`), or set to the current `git rev-parse HEAD` of the target project for `feature_addition`, `pr_url` unset, `open_risks: []`, `phases_completed: []`.

For `feature_addition` (existing git repo): if `.ios-orchestrator/` is not already git-ignored in the target repo (`git check-ignore .ios-orchestrator`), append it to the repo's `.gitignore` (creating the file if needed) as part of initialization. This keeps orchestrator state and screenshots out of the user's repo; for `new_app`, the Developer's scaffold `.gitignore` covers it. This orchestrator-made `.gitignore` change is bookkeeping — exempt from every phase's scope check, like `state.json` (see `role-boundaries.md`).

## Resuming

On invocation, if `.ios-orchestrator/state.json` exists, the orchestrator reads it to determine where to pick up. If `last_commit_sha` is set, before continuing it runs `git rev-parse HEAD` in `target_project_path` (on whichever branch is currently checked out) and compares it to `last_commit_sha`. (For `new_app` runs that haven't reached `pr_creation` yet, `last_commit_sha` is unset, so this drift check is skipped.)

- **Match (or drift check skipped)**: proceed from `phase`/`phase_status` as recorded (if `phase_status: "complete"`, advance to the next phase in sequence; if `"in_progress"`, re-dispatch that phase using the original inputs, including `interview_output`/`architecture_summary` from `state.json` for the Architect).
- **Mismatch**: flag the drift to the user — show `last_commit_sha`, the current HEAD, and a one-line `git log` of the commits in between — and ask via `AskUserQuestion` whether to: proceed anyway (treating the new commits as part of this run's work), re-run the current phase from scratch, or have the Architect re-scope first (jumps back to the `architect` phase).
