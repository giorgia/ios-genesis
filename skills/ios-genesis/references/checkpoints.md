# Checkpoints

After every phase (subagent dispatch) completes, the orchestrator runs this procedure before moving to the next phase. See `state-schema.md` for the state file fields referenced here.

## 1. Update state.json

- Set `phase` to the phase that just ran, `phase_status: "complete"`.
- Append an entry to `phases_completed` (with `phase`, `completed_at`, `summary` from the subagent's report, and `artifact`).
- For `developer`/`pr_creation` phases, update `last_commit_sha` to the new `git rev-parse HEAD`.
- For `pr_creation`, set `pr_url`.
- For `code_review`, increment `review_round` by 1 (it is monotonic and capped at 2 — see `state-schema.md` and `pr-review-flow.md` for the full lifecycle).
- If the subagent's report includes `screens_affected` (architect only), set it.
- For each risk/blocker in the subagent's report, append a new entry to `open_risks` with the next `risk-N` id, `phase` set to the current phase, `raised_at` set to the current time, and the reported `description`.
- If the subagent's report references an existing `open_risks` entry's `id` as resolved, remove that entry from `open_risks`.

## 2. Run the scope check

See `role-boundaries.md` for the per-phase expected-path patterns and git-check method. Any out-of-pattern changes become a new `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional"), added to `state.json` as part of step 1 above (do this before presenting the summary, so it shows up in step 3).

## 3. Present the summary to the user

Present:
- A brief description of what the phase produced or changed (e.g. "Architect wrote `docs/architecture.md` - 3 modules: Networking, Persistence, UI." or "Developer implemented the login screen, build succeeded.").
- A **Risks/Blockers** subsection listing every entry currently in `open_risks` (the cumulative list, not just ones raised this phase), each shown as `[id] description (raised during <phase>)`. If `open_risks` is empty, this subsection reads "Risks/Blockers: none".

## 4. Ask the user via AskUserQuestion

Options: **Continue to the next phase** / **Make changes first** / **Stop here**.

- If the user has open risks they want to address, they can mention specific `id`s in their response to "Make changes first" (or, for "Continue", simply note in passing that an `id` is dismissed/resolved - either way, remove that `open_risks` entry from `state.json` once the user has indicated it's handled).
- **Continue to the next phase**: proceed to the next phase in the sequence (see `orchestration-flow.md`). If this phase was the Architect and `screens_affected: true` and `design_mode` is unset, first ask the design-mode question (see `design-mode.md`) before dispatching the next phase.
- **Make changes first**: collect the user's feedback, then re-dispatch the *same* subagent with the original inputs plus the user's feedback appended (and, for subagents that don't retain memory, a summary of what they previously produced from `phases_completed`). After the follow-up dispatch completes, re-run this checkpoint procedure (steps 1-4) from the top.
- **Stop here**: end the run. `state.json` is already up to date (`phase_status: "complete"` for the just-finished phase) so the run can be resumed later via `state-schema.md`'s Resuming procedure.
