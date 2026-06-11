# PR-Based Review Flow

Covers the `pr_creation`, `code_review`, and `merge` phases.

## Prerequisite: gh CLI authenticated

Before reaching `pr_creation`, the orchestrator checks `gh auth status`. If not authenticated, surface a clear message to the user (e.g. "The `gh` CLI isn't authenticated - run `gh auth login`, then re-run `/ios-genesis` to resume from this point.") and stop. `state.json` is unchanged, so resuming re-enters at `pr_creation`.

## pr_creation

Dispatch `ios-developer` with `dispatch_type: create_pr` (see `agents/ios-developer.md`):

- **`new_app`**: `branch_name: "feature/initial-implementation"`. If the target project has no GitHub remote, checkpoint with the user first: ask (via `AskUserQuestion`) whether to create a GitHub repo (public or private) via `gh repo create`. Once a remote exists, proceed with the dispatch.
- **`feature_addition`**: `branch_name: "feature/<slug>"`, where `<slug>` is derived from the change description (lowercase, spaces to hyphens, e.g. "add login screen" -> "add-login-screen").

After the dispatch, run the `developer`/`pr_creation` scope check (see `role-boundaries.md`), update `state.json` (`pr_url`, `last_commit_sha`), and run the standard checkpoint (`checkpoints.md`).

## code_review loop

1. Set `review_round` to 1 in `state.json` (it starts at 0).
2. Dispatch `ios-code-reviewer` with `pr_url`, `review_round`, `architecture_summary`, `design_summary` (if applicable).
3. If the report's `status: approved` -> proceed to `merge`.
4. If `status: changes_requested`:
   a. Dispatch `ios-developer` with `dispatch_type: address_review`, passing `reviewer_comments` (verbatim from the reviewer's report) and `work_summary` (built from `state.json`'s `phases_completed`).
   b. If the developer's changes affect behavior (use judgment based on the developer's report summary), dispatch `ios-test-engineer` with `dispatch_type: retest`, passing `reviewer_comments` and the developer's `summary`.
   c. If `review_round == 1`: increment to 2, pass `previous_comments` (the round-1 reviewer's comments) to the reviewer, and go back to step 2.
   d. If `review_round == 2` and issues remain: stop looping. Surface the unresolved comments to the user at the checkpoint (do not proceed to `merge` automatically) and let the user decide via the standard checkpoint options.
5. Run the standard checkpoint (`checkpoints.md`) after the loop concludes (whether approved or stopped at round 2). In both cases `phase_status` is set to `"complete"` for `code_review` (per `checkpoints.md` step 1) - even when stopped at round 2 with unresolved issues, since the run can be resumed and `code_review` re-entered manually later if the user addresses the remaining comments outside the orchestrator.

## merge

Only reached if `code_review` resulted in `status: approved`. Run `gh pr merge <pr_url> --squash`.

- **Success**: update `state.json` (`phase: "merge"`, `phase_status: "complete"`), run the standard checkpoint.
- **Failure** (conflicts, pending/failed required checks, etc.): surface the `gh` error output to the user as-is - do not retry automatically. The user can resolve the underlying issue (e.g. fix required checks) and ask the orchestrator to retry the merge, which re-enters this step.
