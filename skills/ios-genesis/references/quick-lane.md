# Quick-Fix Lane

The lightweight path for a **small `feature_addition`** change. It collapses the nine-phase pipeline to *classify → one confirmation → implement → test → (visual only if screens) → single-pass review → PR → auto-merge*, cutting the token cost of a bug fix or small tweak that does not need the full pipeline.

**Applies to `feature_addition` only.** `new_app` is always treated as "large" and never enters this lane. A `feature_addition` classified "large" runs the full flow in `orchestration-flow.md` unchanged.

## Classification (pre-step, before the interview)

Before the Step 0 interview, the orchestrator dispatches `ios-architect` with `dispatch_type: classify` (see `agents/ios-architect.md`). The Architect does a quick codebase survey and **returns** (writes no file, builds no task graph):

- `size`: `"small"` or `"large"`
- `scope`: a one-paragraph plain-language description of the change
- `screens_affected`: `true` / `false`
- `estimated_owned_files`: the file paths the change is expected to touch

For issue-driven runs, the fetched issue material (see `issue-driven-runs.md`) is passed into the classify dispatch in place of the raw description.

**Lane selection:**

- `size: "large"` → discard the classify result and run the standard flow: full `superpowers:brainstorming` interview (Step 0) followed by the full nine-phase `feature_addition` sequence in `orchestration-flow.md`. The Architect re-runs in full as phase 1. Persist `lane: "full"`.
- `size: "small"` → enter the quick lane below. Persist `lane: "quick"` at initialization (see `state-schema.md`).

The classify dispatch is one cold Architect call with no file write and no graph construction — far cheaper than the full Architect phase, and for small changes it **replaces** the full interview rather than adding to it.

## Sequence

Initialize `state.json` with `mode: "feature_addition"`, `lane: "quick"`, and the classify result, per `state-schema.md`'s Initialization (git model established as normal — repo, `.gitignore`, working branch `feature/<slug>`).

### 1. Single checkpoint (the only user stop)

Present the classifier's `scope`, fold in at most 1–2 clarifying questions only if genuinely needed, and ask via `AskUserQuestion`:

- **Proceed with quick fix** → the confirmed requirements are persisted (in place of `interview_output`); continue to step 2 and run autonomously through merge.
- **Treat as a larger change** (the user judges it bigger than "small") → **fall back to the full pipeline**: run the full brainstorming interview and the standard nine-phase sequence. Rewrite `lane: "full"` in `state.json`.

No further checkpoints fire inside the quick lane.

### 2. developer (solo, `dispatch_type: implement`)

Dispatch `ios-developer` with `mode: feature_addition`, `target_project_path`, the confirmed scope text as `architecture_summary`, and `estimated_owned_files` as guidance. This is the **v0.2.0 solo contract** — single-task, no task graph, no waves: the agent writes and builds itself, up to its normal 3 build attempts. The dispatch carries the short scope text + file pointers, not a full `architecture.md`/`design.md`.

### 3. test_engineer (solo, `dispatch_type: test`)

Dispatch `ios-test-engineer` with `mode: feature_addition`, `target_project_path`, the scope text, and `developer_summary` from step 2. Solo contract: it writes tests covering the changed files and runs them itself (no registration pre-step wave, no parallel `test-without-building`).

### 4. visual_verification — only if `screens_affected`

Run **only when the classifier set `screens_affected: true`**. Otherwise skip entirely. When it runs, it's the single-task visual verification loop from `orchestration-flow.md` (solo verifier, capped at 2 rounds, `interactive` detected as usual). Otherwise omit the phase — a purely internal change has nothing to verify visually.

### 5. code_review — single pass

One `code_review` dispatch per `pr-review-flow.md`. Findings are addressed in a **single** developer round, then the phase concludes — no multi-round review loop in the quick lane.

### 6. pr_creation → merge (auto)

Open the PR (`branch_name: "feature/<slug>"`) per `pr-review-flow.md`, then — because the user confirmed up front — **auto-merge** via the `merge` phase if build + tests + review all passed. Issue-driven `Closes #N` behavior (v0.4.0) still applies.

On success, report the run complete: the merged PR link, what changed, tests result, and any `open_risks`.

## Failure handling (autonomous after the checkpoint)

The lane runs unattended after the single confirmation, so a genuine blocker **stops** the run rather than merging anyway. In every case the orchestrator reports what failed and leaves `state.json` resumable; it never merges on a failed safety phase.

- **developer** exhausts its 3 build attempts → stop, report the build failure. No merge.
- **test_engineer** tests still failing after its fix rounds → stop and report. No merge.
- **code_review** surfaces blocking issues the single fix round does not resolve → stop and report. No merge.
- **visual_verification** (screens only) unresolved after 2 rounds → record `open_risks` and stop before merge (a visual regression should not auto-merge).

## Resume

A quick-lane run resumes into its recorded `phase` like any other run (see `state-schema.md`'s Resuming). The single checkpoint is already passed once the lane is running, so resume re-enters the autonomous sequence at the recorded phase — it does not re-classify (the classify result is persisted) and does not re-ask the confirmation.
