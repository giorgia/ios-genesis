# Checkpoints

After every phase (subagent dispatch) completes, the orchestrator runs this procedure before moving to the next phase. See `state-schema.md` for the state file fields referenced here.

## 1. Update state.json

- Set `phase` to the phase that just ran, `phase_status: "complete"`.
- Append an entry to `phases_completed` (with `phase`, `completed_at`, `summary` from the subagent's report, and `artifact`).
- **Multi-task graphs:** update each task's `status` (`complete`, `failed`, or `dropped`) and `results` fields (`build_status`, `design_status`, `verify_status`, `tests_status`, etc.) in `task_graph.tasks` from the subagent reports.
- For `code_review` and `merge` phases, update `last_commit_sha` to the current `git rev-parse HEAD` — this captures, respectively, any `address_review` fixes pushed during the `code_review` loop, and the squash-merge commit at `merge`. For all other phases, `last_commit_sha` is updated in step 4 when the wip commit lands.
- For `pr_creation`, set `pr_url`.
- For `code_review`, persist `review_round` as already set by the `code_review` loop (see `pr-review-flow.md`) - this checkpoint runs once after the loop concludes, so do not increment it again here. It is monotonic and capped at 2 (see `state-schema.md`).
- For `visual_verification`, persist `verification_round` as already set by the verification loop (see `orchestration-flow.md`) - this checkpoint runs once after the loop concludes, so do not increment it again here. It is monotonic and capped at 2, like `review_round`.
- If the subagent's report includes `screens_affected` (architect only), set it.
- For `architect` in `feature_addition` mode (no file artifact - see `agents/ios-architect.md`), additionally persist the Architect's full scope-summary text as `architecture_summary` in `state.json`, separate from the short `summary` stored in `phases_completed`. Later phases (`ui_designer`, `developer`, `test_engineer`, `code_reviewer`) need this full text and the Architect has no memory to re-derive it.
- For each risk/blocker in the subagent's report, append a new entry to `open_risks` with the next `risk-N` id, `phase` set to the current phase, `raised_at` set to the current time, and the reported `description`. The `description` must lead with the impact on the shipped app, if any — e.g. "the Custom chip is clipped in the app; the Figma mockup edit that would have fixed it was never applied", not "the Figma mockup still shows the clipped chip". A risk phrased as a mockup/tooling footnote while the product is affected will mislead every later summary that quotes it.
- If the subagent's report references an existing `open_risks` entry's `id` as resolved, remove that entry from `open_risks`.

## 2. Run the scope check

See `role-boundaries.md` for the per-phase expected-path patterns and git-check method. Any out-of-pattern changes become a new `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional"), added to `state.json` as part of step 1 above (do this before presenting the summary, so it shows up in step 5).

## 3. Resolve failures (multi-task graphs only)

Skip this step for single-task graphs — the v0.2.0 checkpoint applies unchanged.

Siblings always run to completion before this step fires. For each task with `status: "failed"` in the current phase, present the failure and ask the user to choose:

- **Retry:** re-dispatch the task's agent with sibling summaries as additional context. Multiple retried tasks re-enter the wave scheduler and dispatch concurrently up to the cap. If remaining waves (e.g. the integration wave) have not yet run, the checkpoint will legitimately fire again once they complete — the one-gate invariant is per *pass*, not per calendar phase.
- **Drop:** revert the task's `owned_files` to the last wip commit — `git checkout <last_commit_sha> -- <tracked paths>`, then delete any untracked files within those `owned_files` prefixes — so no non-compiling code from the dropped task survives into later integration builds. After applying the reverts, run one integration build (`xcodegen generate` + `xcodebuild build`); a failure here is an integration defect surfaced at the same checkpoint (the surviving code no longer compiles without the dropped files) — resolve it before proceeding, to preserve the invariant that wip commits are always buildable. Then:
  - Set `status: "dropped"` in `task_graph.tasks`.
  - Exclude the dropped task from all subsequent phase projections; dependents treat the dropped dependency as satisfied (the integration task simply omits wiring it).
  - Append an `open_risks` entry describing what was dropped and why.

  **Warn before accepting a drop whose task still has dependents in later projections.** Examples: dropping `foundation` orphans every screen and feature task (nothing else can build); dropping `integration` ships unwired screens. Require explicit confirmation before proceeding.

- **Stop:** end the run. `state.json` is up to date (`phase_status: "complete"`, failed tasks marked `failed`); resume via `state-schema.md`'s Resuming procedure.

The step 4 wip commit happens only once every failed task is resolved (retried to success or dropped-and-reverted) — wip commits are always buildable. **Resume mid-wave:** tasks found `in_progress` on resume reset to `pending` and re-dispatch fresh; agents are instructed to inspect `owned_files` for partial prior work before writing.

## 4. Commit

Create a `wip(<phase>): <one-liner>` commit — this is the **last state-mutating act** of the checkpoint. After committing, set `last_commit_sha` to `git rev-parse HEAD`. Note: for fanned-out phases, per-wave `wip(<phase>/wave-N)` commits made at each wave-end build are separate from this post-phase checkpoint commit.

Skip this step when `git status --porcelain` is empty — never attempt an empty commit. Typical cases where the working tree is clean at this point: `code_review` (address_review fixes are remote pushes already captured in step 1), `merge` (squash-merge commit captured in step 1), clean `visual_verification` passes where no `address_visual` fix landed locally, and survey-only architect phases in `feature_addition` mode that wrote no tracked files.

## 5. Present the summary to the user

Present:
- **Multi-task graphs:** a per-task results table — one row per task in the phase's projection showing task id, title, outcome (✓ complete / ✗ failed / — skipped), and a one-liner from the subagent's report.
- A summary of what the phase produced or changed - not just a one-line status. For phases that write a doc (`docs/architecture.md`, `docs/design.md`, `docs/release-checklist.md`), surface the doc's actual key content (e.g. module/screen names and responsibilities, key architectural decisions, checklist items and their status) so the user can evaluate it without opening the file themselves. For `architect` in `feature_addition` mode (no file artifact), surface the same kind of content from the persisted `architecture_summary` scope-summary text instead. For phases that don't write a doc (`developer`, `test_engineer`, `pr_creation`, `code_review`, `merge`), describe concretely what changed (files touched, build/test results, PR link, review verdict). For `visual_verification`, the summary must state the verdict (pass / issues found and fixed / issues remaining / skipped and why), reference the screenshot path(s) under `.ios-orchestrator/screenshots/`, and list any screens the verifier reported as `unverified`.
- A **Risks/Blockers** subsection listing every entry currently in `open_risks` (the cumulative list, not just ones raised this phase), each shown as `[id] description (raised during <phase>)`. If `open_risks` is empty, this subsection reads "Risks/Blockers: none".
- **Multi-task graphs:** a wave preview for the next phase — projection (which tasks participate), dependency order, cap, and wave count. Example: "developer: 8 tasks, cap 3 → foundation solo, then 3+3+1 screen waves, then integration solo". The post-`architect` checkpoint additionally renders the full task graph with each task's `ui_impact` flag so the user can correct any mis-classified tasks before the design phase begins.

## 6. Ask the user via AskUserQuestion

Options: **Continue to the next phase** / **Continue with different cap** (multi-task graphs only) / **Make changes first** / **Stop here**.

- If the user has open risks they want to address, they can mention specific `id`s in their response to "Make changes first" (or, for "Continue", simply note in passing that an `id` is dismissed/resolved - either way, remove that `open_risks` entry from `state.json` once the user has indicated it's handled).
- **Continue to the next phase**: proceed to the next phase in the sequence (see `orchestration-flow.md`). If this phase was the Architect and `screens_affected: true` and `design_mode` is unset, first ask the design-mode question (see `design-mode.md`) before dispatching the next phase.
- **Continue with different cap**: prompt for the new cap value, update `task_graph.cap` in `state.json`, then proceed as "Continue to the next phase".
- **Make changes first**: collect the user's feedback, then re-dispatch the *same* subagent with the original inputs plus the user's feedback appended (and, for subagents that don't retain memory, a summary of what they previously produced from `phases_completed`). After the follow-up dispatch completes, re-run this checkpoint procedure (steps 1-6) from the top.
- **Stop here**: end the run. `state.json` is already up to date (`phase_status: "complete"` for the just-finished phase) so the run can be resumed later via `state-schema.md`'s Resuming procedure.
