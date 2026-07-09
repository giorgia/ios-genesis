# Checkpoints

After every phase (subagent dispatch) completes, the orchestrator runs this procedure before moving to the next phase. See `state-schema.md` for the state file fields referenced here.

## 1. Update state.json

- Set `phase` to the phase that just ran, `phase_status: "complete"`.
- Append an entry to `phases_completed` (with `phase`, `completed_at`, `summary` from the subagent's report, and `artifact`).
- For `pr_creation`, `code_review`, and `merge` phases, update `last_commit_sha` to the current `git rev-parse HEAD` - this captures, respectively, the branch/PR commit (and, for `new_app`, the `git init` initial commit) at `pr_creation`, any `address_review` fixes pushed during the `code_review` loop, and the squash-merge commit at `merge`. (`developer`/`implement` never commits, so its checkpoint doesn't touch `last_commit_sha`.)
- For `pr_creation`, set `pr_url`.
- For `code_review`, persist `review_round` as already set by the `code_review` loop (see `pr-review-flow.md`) - this checkpoint runs once after the loop concludes, so do not increment it again here. It is monotonic and capped at 2 (see `state-schema.md`).
- For `visual_verification`, persist `verification_round` as already set by the verification loop (see `orchestration-flow.md`) - this checkpoint runs once after the loop concludes, so do not increment it again here. It is monotonic and capped at 2, like `review_round`.
- If the subagent's report includes `screens_affected` (architect only), set it.
- For `architect` in `feature_addition` mode (no file artifact - see `agents/ios-architect.md`), additionally persist the Architect's full scope-summary text as `architecture_summary` in `state.json`, separate from the short `summary` stored in `phases_completed`. Later phases (`ui_designer`, `developer`, `test_engineer`, `code_reviewer`) need this full text and the Architect has no memory to re-derive it.
- For each risk/blocker in the subagent's report, append a new entry to `open_risks` with the next `risk-N` id, `phase` set to the current phase, `raised_at` set to the current time, and the reported `description`. The `description` must lead with the impact on the shipped app, if any — e.g. "the Custom chip is clipped in the app; the Figma mockup edit that would have fixed it was never applied", not "the Figma mockup still shows the clipped chip". A risk phrased as a mockup/tooling footnote while the product is affected will mislead every later summary that quotes it.
- If the subagent's report references an existing `open_risks` entry's `id` as resolved, remove that entry from `open_risks`.

## 2. Run the scope check

See `role-boundaries.md` for the per-phase expected-path patterns and git-check method. Any out-of-pattern changes become a new `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional"), added to `state.json` as part of step 1 above (do this before presenting the summary, so it shows up in step 3).

## 3. Present the summary to the user

Present:
- A summary of what the phase produced or changed - not just a one-line status. For phases that write a doc (`docs/architecture.md`, `docs/design.md`, `docs/release-checklist.md`), surface the doc's actual key content (e.g. module/screen names and responsibilities, key architectural decisions, checklist items and their status) so the user can evaluate it without opening the file themselves. For `architect` in `feature_addition` mode (no file artifact), surface the same kind of content from the persisted `architecture_summary` scope-summary text instead. For phases that don't write a doc (`developer`, `test_engineer`, `pr_creation`, `code_review`, `merge`), describe concretely what changed (files touched, build/test results, PR link, review verdict). For `visual_verification`, the summary must state the verdict (pass / issues found and fixed / issues remaining / skipped and why), reference the screenshot path(s) under `.ios-orchestrator/screenshots/`, and list any screens the verifier reported as `unverified`.
- A **Risks/Blockers** subsection listing every entry currently in `open_risks` (the cumulative list, not just ones raised this phase), each shown as `[id] description (raised during <phase>)`. If `open_risks` is empty, this subsection reads "Risks/Blockers: none".

## 4. Ask the user via AskUserQuestion

Options: **Continue to the next phase** / **Make changes first** / **Stop here**.

- If the user has open risks they want to address, they can mention specific `id`s in their response to "Make changes first" (or, for "Continue", simply note in passing that an `id` is dismissed/resolved - either way, remove that `open_risks` entry from `state.json` once the user has indicated it's handled).
- **Continue to the next phase**: proceed to the next phase in the sequence (see `orchestration-flow.md`). If this phase was the Architect and `screens_affected: true` and `design_mode` is unset, first ask the design-mode question (see `design-mode.md`) before dispatching the next phase.
- **Make changes first**: collect the user's feedback, then re-dispatch the *same* subagent with the original inputs plus the user's feedback appended (and, for subagents that don't retain memory, a summary of what they previously produced from `phases_completed`). After the follow-up dispatch completes, re-run this checkpoint procedure (steps 1-4) from the top.
- **Stop here**: end the run. `state.json` is already up to date (`phase_status: "complete"` for the just-finished phase) so the run can be resumed later via `state-schema.md`'s Resuming procedure.
