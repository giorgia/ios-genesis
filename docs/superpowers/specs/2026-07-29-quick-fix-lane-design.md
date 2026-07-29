# ios-genesis v0.6.0 — Quick-Fix Lane

## Problem

`/ios-genesis` has exactly one execution path for a `feature_addition`, and it is the heavy one. Whether the change is a one-line bug fix or a whole new feature, the run walks all nine phases — architect → ui_designer → developer → visual_verification → test_engineer → pr_creation → code_review → merge → release_manager — each with its own user checkpoint. The token cost is effectively flat at "maximum" regardless of the size of the change, so a small bug fix can burn an entire session's limits.

Four amplifiers drive this, in rough order of impact:

1. **No severity routing.** Every `feature_addition` runs the full nine-phase pipeline. A typo fix pays for the Architect interview, task-graph validation, and every downstream phase.
2. **Cold subagents + full-context re-shipping.** `SKILL.md` mandates that *every dispatch include all context the subagent needs* (`architecture_summary`, `design_summary`, relevant state). That context is re-embedded into the developer, then the verifier, then the test engineer, then the reviewer — O(phases × context), each agent starting cold.
3. **Unconditional step-0 interview.** The `superpowers:brainstorming` interview runs in full even for a trivial change.
4. **Re-dispatch loops.** Up to 3 developer build rounds, 2 visual rounds, plus the code-review loop, each re-carrying the whole context.

This feature adds a **quick-fix lane**: a lightweight path for small `feature_addition` changes that collapses the pipeline to *classify → one confirmation → implement → test → (visual only if screens) → single-pass review → PR → auto-merge*, attacking all four amplifiers at once. It does NOT change `new_app` (always "large") or the full `feature_addition` pipeline for genuinely large changes.

## Decisions made during brainstorming

- **Scope: `feature_addition` only.** `new_app` is always classified "large" and is untouched. The full pipeline is unchanged for large feature additions.
- **Routing: the Architect classifies, via a cheap pre-classify step run *before* brainstorming.** A new `dispatch_type: classify` Architect dispatch does a quick codebase survey and returns `size` (`small`/`large`) plus a one-paragraph scope, `screens_affected`, and an estimated `owned_files` — no `architecture.md` write, no task graph. Running it before the interview is what lets the interview itself be slimmed for small changes.
- **Interview: slim for small changes.** When the classifier returns `small`, the full brainstorming interview is replaced by the single up-front confirmation (below), which folds in 1–2 clarifying questions. When it returns `large`, the normal full brainstorming interview runs and the full pipeline follows.
- **Safety net: tests + single-pass review.** The quick lane keeps `test_engineer` (tests for changed files) and one `code_review` pass. It drops `ui_designer`, `release_manager`, and all fan-out; `visual_verification` runs only if `screens_affected`.
- **One checkpoint.** A single confirmation after classification ("this is small — here's the plan; proceed?"). After that the lane runs autonomously. The user can answer "it's actually bigger," which falls the run back to the full pipeline (full brainstorming + all phases).
- **Auto-merge.** After the confirmation, the lane runs autonomously through `merge` (reusing `pr-review-flow.md`) if build + tests + review all pass.
- **Ships as v0.6.0.**

## 1. Classification (new pre-step, `feature_addition` only)

Runs only for `mode: feature_addition`. `new_app` skips classification entirely and proceeds as today (always "large").

- **Dispatch:** before the step-0 interview, the orchestrator dispatches `ios-architect` with `dispatch_type: classify`, `target_project_path`, and the raw `description` (and, for issue-driven runs, the fetched issue material). The agent does a quick codebase survey and **returns** (writes nothing):
  - `size`: `"small"` or `"large"`
  - `scope`: a one-paragraph plain-language description of the change
  - `screens_affected`: `true`/`false`
  - `estimated_owned_files`: the file paths the change is expected to touch
- **Classification guidance (in the agent prompt):** `small` = a localized change confined to a bounded set of existing files, adding no new screen and no new architectural component (bug fixes, copy/string changes, small logic tweaks, config changes). Anything that adds a screen, introduces a new module/component, or spans many files is `large`. When in doubt, classify `large` (the safe default — a large classification never under-tests a change).
- **Cost note:** this is one cold Architect dispatch with no `architecture.md` write and no task-graph construction — far cheaper than the full Architect phase, and it replaces (does not add to) the full interview for small changes.

## 2. Lane selection

- `size: "large"` → hand off to the existing flow: run the full `superpowers:brainstorming` interview (step 0) and the full nine-phase `feature_addition` pipeline exactly as today. The classify result is discarded (the Architect re-runs in full as phase 1). Nothing else changes.
- `size: "small"` → enter the quick lane (§3). Persist `lane: "quick"` in `state.json` at initialization.

## 3. Quick lane sequence

Initialize `state.json` with `mode: "feature_addition"`, `lane: "quick"`, and the classify result, per `state-schema.md`'s Initialization (git model established as normal). Then:

1. **Single checkpoint (the only user stop).** The orchestrator presents the classifier's `scope`, folds in at most 1–2 clarifying questions if genuinely needed, and asks via `AskUserQuestion`: proceed with the quick fix, or treat it as a larger change. The response persists as the run's requirements (in place of `interview_output`).
   - "Proceed" → continue to step 2, autonomously through merge.
   - "It's actually bigger" → **fall back to the full pipeline**: run the full brainstorming interview and the standard nine-phase sequence. Rewrite `lane: "full"` in `state.json`.
2. **developer (solo, `dispatch_type: implement`).** Dispatched with the scope text, `estimated_owned_files`, and `target_project_path`. Solo contract (single-task, no fan-out): the agent writes and builds itself, up to its normal 3 build attempts. No task graph, no waves. Dispatch carries the short scope text + file pointers — not a full `architecture.md`/`design.md`.
3. **test_engineer (solo, `dispatch_type: test`).** Writes and runs tests covering the changed files, self-building and self-running (v0.2.0 solo contract — no registration pre-step wave, no parallel `test-without-building`).
4. **visual_verification.** Runs **only if `screens_affected: true`** (solo verifier, existing single-task semantics, capped at 2 rounds). Otherwise skipped entirely.
5. **code_review — single pass.** One `code_review` dispatch per `pr-review-flow.md`; findings are addressed in a single developer round, then the phase concludes. No multi-round review loop.
6. **pr_creation → merge.** Open the PR (`branch_name: "feature/<slug>"`) and, since the user confirmed up front, **auto-merge** via `pr-review-flow.md`'s merge phase if build + tests + review passed. For issue-driven runs, the `Closes #N` behavior from v0.4.0 still applies.

No per-phase checkpoints fire inside the quick lane; the run reports completion after merge (or surfaces a blocking failure — see §5).

## 4. State

- New field `lane: "quick" | "full"` on `state.json`, set at initialization from the classification (defaults to `"full"` for `new_app` and for any run that skips classification, preserving today's behavior).
- The classify result (`size`, `scope`, `screens_affected`, `estimated_owned_files`) is persisted so a resumed quick-lane run does not re-classify.
- Resume: a quick-lane run resumes into its recorded phase like any other run; because there is only one checkpoint (already passed once the lane is running), resume re-enters the autonomous sequence at the recorded phase.

## 5. Failure handling

The quick lane is autonomous after the single checkpoint, so a genuine blocker must stop it rather than silently proceed:

- **developer** exhausts its 3 build attempts → stop, report the build failure, leave `state.json` resumable. No auto-merge.
- **test_engineer** tests fail after its fix rounds → stop and report; do not merge.
- **code_review** single pass surfaces blocking issues the single fix round doesn't resolve → stop and report; do not merge.
- **visual_verification** (screens only) unresolved after 2 rounds → record `open_risks` and stop before merge (a visual regression should not auto-merge).

In every stop case the orchestrator reports what failed and leaves the run resumable; it never merges on a failed safety phase.

## 6. Files changed

- `references/quick-lane.md` **(new)** — the full quick-lane sequence and failure handling. Loaded only on quick-lane runs (per `SKILL.md`'s "load as needed"), so it adds zero tokens to normal runs.
- `references/orchestration-flow.md` — add the classify pre-step and lane selection; point to `quick-lane.md` for the small path.
- `skills/ios-genesis/SKILL.md` — top-level control flow: classification selects the lane; note the new reference doc.
- `references/state-schema.md` — add `lane`, persist the classify result, note resume behavior.
- `references/checkpoints.md` — note the quick-lane single-checkpoint rule (no per-phase checkpoints).
- `agents/ios-architect.md` — add the `dispatch_type: classify` mode and its return contract.
- `README.md` — document the quick lane; version bump to **v0.6.0**.

## 7. Out of scope (deferred)

- **Classifier as a separate lightweight agent.** Reuses the Architect (`classify` mode) rather than adding a new agent, per the brainstorming decision.
- **Auto-detecting "small" mid-run** beyond the single up-front classification (e.g. the developer discovering the change is bigger and self-escalating). The one confirmation + "it's actually bigger" fallback covers the underestimation case.
- **Trimming per-dispatch context in the full pipeline** (amplifier #2 for large runs). The quick lane removes most of it by removing phases and fan-out; a dedicated context-pointer pass for the full pipeline is a separate follow-up.
- **Fan-out inside the quick lane.** Small changes are single-task by definition; the quick lane is deliberately solo-only.
