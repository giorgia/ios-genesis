# State File Schema

`<target-project-path>/.ios-orchestrator/state.json` is written by the orchestrator at initialization, at wave ends, and at phase checkpoints. It enables resuming a run later and tracks cumulative risks/blockers.

## Schema

```json
{
  "mode": "new_app",
  "lane": "full",
  "interview_output": "Build a single-screen counter app...",
  "phase": "visual_verification",
  "phase_status": "in_progress",
  "review_round": 0,
  "screens_affected": true,
  "design_mode": "figma",
  "design_sources": [],
  "source_issues": [{ "number": 12, "title": "Best streak captures last, not the max", "url": "https://github.com/owner/repo/issues/12" }],
  "app_scheme": "TipTop",
  "task_graph": {
    "cap": 3,
    "tasks": [
      {
        "id": "T1",
        "title": "Foundation: shared models, app entry, theme",
        "kind": "foundation",
        "owned_files": ["App/Models/", "App/TipTopApp.swift", "App/Theme/"],
        "depends_on": [],
        "ui_impact": false,
        "status": "complete",
        "results": {
          "build_status": "success"
        }
      },
      {
        "id": "T2",
        "title": "Home screen",
        "kind": "screen",
        "owned_files": ["App/Views/Home/"],
        "depends_on": ["T1"],
        "ui_impact": true,
        "status": "in_progress",
        "results": {
          "design_status": "complete",
          "design_reference": "https://figma.com/file/abc",
          "build_status": "success",
          "verify_status": "pending",
          "verification_round": 0
        }
      }
    ]
  },
  "last_commit_sha": "a1b2c3d4...",
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
    },
    {
      "phase": "ui_designer",
      "completed_at": "2026-06-11T11:00:00Z",
      "summary": "1 screen designed: Home. Figma file linked, all tokens exported.",
      "artifact": "docs/design.md"
    },
    {
      "phase": "developer",
      "completed_at": "2026-06-11T13:30:00Z",
      "summary": "T1 (foundation) and T2 (Home screen) implemented. Build passing on both tasks.",
      "artifact": "sources+project.yml"
    }
  ]
}
```

## Field reference

- `mode`: `"new_app"` or `"feature_addition"`. Set once, at initialization, based on whether `.ios-orchestrator/state.json` existed at the start of the run.
- `lane`: `"quick"` or `"full"`. Set once, at initialization, from the Architect's classify pass (see `quick-lane.md`). `"quick"` only for a `feature_addition` classified `small`; `"full"` for `new_app`, for a `feature_addition` classified `large`, for any run that skips classification, and for pre-0.6.0 state files (where the key is absent — treat missing as `"full"`). A `"quick"` run rewrites this to `"full"` if the user chooses "treat as a larger change" at the single checkpoint. `classify_result` holds the pre-pass output (`size`, `scope`, `screens_affected`, `estimated_owned_files`) so a resumed quick-lane run does not re-classify; present only when a classify pass ran, omitted otherwise.
- `interview_output`: the requirements/approach/design summary approved at the end of the orchestrator's Step 0 interview (see `orchestration-flow.md`). Set once, at initialization, before the Architect's first dispatch — this lets a resume re-dispatch the Architect with the same input if the run stopped before the Architect's checkpoint completed.
- `architecture_summary`: only present when `mode: "feature_addition"`. A **pointer** to `.ios-orchestrator/scope.md` (v0.7.0+) — the Architect writes the scope there with `## <section>` anchors (see `agents/ios-architect.md`, `references/context-contract.md`), rather than storing the body inline in `state.json`. Later phases (`ui_designer`, `developer`, `test_engineer`, `code_reviewer`) are dispatched with `.ios-orchestrator/scope.md#<section>` refs and read their own slice — the orchestrator never holds the body. For `mode: "new_app"`, the scope lives in `docs/architecture.md` (addressed as `docs/architecture.md#<Section>`) and this key is omitted. **Back-compat:** a pre-0.7.0 state file may carry the full scope text inline here instead of a pointer; readers accept either (inline text or a `scope.md` pointer), and new runs write the pointer.
- `phase`: one of `architect`, `ui_designer`, `developer`, `visual_verification`, `test_engineer`, `pr_creation`, `code_review`, `merge`, `release_manager` — the phase currently in progress or last completed.
- `phase_status`: `"in_progress"` or `"complete"`.
- `review_round`: current round of the PR review loop (see `pr-review-flow.md`). Monotonically increasing across the PR's lifecycle: `0` before the first review dispatch, `1` for the first review, `2` for the second (the loop is capped at 2 rounds — see `pr-review-flow.md`).
- `verification_round`: current round of the visual verification loop (see `orchestration-flow.md`). Monotonic, analogous to `review_round`: `0` before the first verifier dispatch, `1` for the first verification, `2` for the second (the loop is capped at 2 rounds). The phase's `phases_completed` artifact is `.ios-orchestrator/screenshots/` (or `"none"` if the phase was skipped).
- `screens_affected`: `true`, `false`, or `null` if not yet determined (set by the Architect's report). Determines whether `ui_designer` runs and whether the design-mode question is asked (see `design-mode.md`).
- `design_mode`: `"text"`, `"figma"`, `"claude_design"`, or `"bring_your_own"`. Set at one of two points (see `design-mode.md`): `"bring_your_own"` is set at initialization when the step-0 interview finds the user already has designs; the create-fresh modes (`"text"` / `"figma"` / `"claude_design"`) are set later, at the Architect's checkpoint, and are only meaningful when `screens_affected: true`. Unset (key omitted) until whichever point applies.
- `design_sources`: list of file paths/URLs to user-provided designs. Populated when `design_mode` is `"bring_your_own"` (normally at initialization, from the step-0 interview); empty otherwise.
- `source_issues`: list of `{ "number": int, "title": string, "url": string }` for the GitHub Issues a `feature_addition` run was built from (see `issue-driven-runs.md`). Present only for issue-driven runs; **unset (key omitted)** otherwise. Written at initialization from the Step 0 selection; read before the `create_pr` dispatch to build the `Closes #N` list. Carried through resume unchanged.
- `app_scheme`: the Xcode scheme used to build/launch the app. For `new_app`: set from the Developer's `implement` report (it matches `project.yml`'s `name:`, which remains the authoritative source on resume). For `feature_addition`: unset (key omitted) — the Visual Verifier is dispatched with `"discover"` and resolves the scheme itself via `xcodebuild -list`.
- `task_graph`: present for v0.3.0 runs; omitted in pre-0.3.0 state files (which resume with the legacy sequential flow including the legacy git model). Object with:
  - `cap`: int (default `3`). Maximum concurrent tasks dispatched per wave.
  - `tasks`: ordered list of task objects. Each task has:
    - `id`: string (`"T1"`, `"T2"`, …).
    - `title`: human-readable task description.
    - `kind`: `foundation` | `screen` | `feature` | `integration`. Cardinality: 0 or 1 `foundation`, 0 or 1 `integration`.
    - `owned_files`: exclusive set of literal directory prefixes or single file paths. Disjointness rule: no owned path may be a path-prefix of another task's owned path.
    - `depends_on`: list of task `id`s. Must form a DAG (a cycle would deadlock the wave scheduler).
    - `ui_impact`: boolean. `screen` tasks are always `true`; drives phase participation (ui_designer, visual_verification).
    - `status`: `pending` | `in_progress` | `complete` | `failed` | `dropped`.
    - `results`: object accumulating per-phase outcomes as the task progresses. Fields and value sets: `design_status`: `pending|complete` (set by the orchestrator when the task's designer report arrives); `design_reference`: URL or file path — a list when `bring_your_own` maps several sources to one task (for `figma`, set alongside `design_status`; for `bring_your_own`, set at mapping time); `build_status`: `pending|success|failed` (set by the orchestrator from the wave-end integration build, or the agent's own build for solo waves); `verify_status`: `pass|issues_found|skipped|deferred_to_device` (`deferred_to_device` means every `sim`-drivable flow passed but a `device`-tagged flow needs real-device confirmation — see `references/interactive-verification.md`; the deferred flow, and any `unverified_no_mcp` flow, is also recorded as an `open_risks` entry rather than a new persisted field); `verification_round`: `1|2`; `tests_status`: `pass|failed|skipped` (set by the orchestrator from its `test-without-building` run in fan-out, or the agent's report in solo waves).
  - Written by the orchestrator only, after validating the Architect-reported graph (disjointness + DAG). On validation failure: re-dispatch the Architect with the defect named (max 2 retries), then surface at the checkpoint.
  - **Single-task graphs**: execution degenerates to the v0.2.0 sequential flow; top-level `verification_round`/`review_round` keep their existing meaning. **Multi-task graphs**: `verification_round` lives in each task's `results`; `review_round` remains top-level in all modes (code_review is whole-run). **Pre-0.3.0 state files** (no `task_graph` key): resume with the legacy sequential flow unchanged, including the legacy git model. A resume with no `task_graph` but `last_commit_sha` set while `phase` is `architect` is a v0.3.0 pre-graph resume — git model already initialized (working branch exists); do NOT route it to the legacy pr_creation init path.
- `last_commit_sha`: HEAD of the working branch as of the last orchestrator commit. Updated at every orchestrator commit — each `wip(<phase>)` checkpoint commit and each `wip(<phase>/wave-N)` wave-build commit. Set at git initialization (on the working branch after the initial commit) and kept current throughout the run. All run commits land on the working branch until `merge`; post-merge phases (`release_manager`) commit to the default branch, and `last_commit_sha` tracks those too. Pre-0.3.0 state files may have this unset for `new_app` runs that had not yet reached `pr_creation`; the legacy resume path handles that case (see Resuming, below).
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

For a brand-new run (`mode: new_app`, or `feature_addition` against a project with no existing state file), the orchestrator creates `.ios-orchestrator/state.json` with: `mode` set appropriately, `lane` set from the classify pass (`"quick"` for a `feature_addition` classified `small`, `"full"` otherwise — see `quick-lane.md`) with `classify_result` persisted when a classify pass ran, `interview_output` set from Step 0's interview result (for a quick-lane run, from the confirmed scope at the single checkpoint instead of a full interview), `phase: "architect"`, `phase_status: "in_progress"`, `review_round: 0`, `verification_round: 0`, `screens_affected: null` (unknown until the Architect reports), `design_mode` set to `"bring_your_own"` if the step-0 interview found existing designs (otherwise unset until the Architect's checkpoint), `design_sources` set to the captured paths/URLs in that case (otherwise `[]`), `source_issues` set to the issues selected in the Step 0 interview if this is an issue-driven `feature_addition` run (otherwise unset), `last_commit_sha` set to the HEAD of the working branch after git initialization (see below), `pr_url` unset, `open_risks: []`, `phases_completed: []`.

**Git initialization (post-interview, both modes):** `git init` if no repo exists — applies to both `new_app` and `feature_addition` (a feature can be added to a project that was never put in source control). First act in both modes: ensure `.gitignore` contains `.ios-orchestrator/` — create the file if it does not exist; otherwise append if not already ignored (`git check-ignore .ios-orchestrator`). This replaces the feature_addition-only carve-out from v0.2.0 and keeps orchestrator state and screenshots out of the repo in all modes. If the repo is empty (after `git init` in either mode), make an initial commit on the default branch. Then create and switch to the working branch: `feature/initial-implementation` for `new_app`, `feature/<slug>` for `feature_addition` (slug derived from the interview output); if the branch name is already taken, suffix `-2`. Set `last_commit_sha` to `git rev-parse HEAD` on the working branch. This `.gitignore` change is bookkeeping — exempt from every phase's scope check, like `state.json` (see `role-boundaries.md`). Two other files live under gitignored `.ios-orchestrator/` and are likewise ephemeral and scope-check-exempt: `symbols.txt` (the repo map, regenerated by the orchestrator on the build rhythm) and `scope.md` (the `feature_addition` scope artifact the Architect writes — see `architecture_summary` below). Both are described in `references/context-contract.md`.

**feature_addition edges:** the dirty-tree and non-default-branch interview questions apply only when a repo already existed before this run (i.e. `git init` was not run above). If the current checkout is on a non-default branch, or if the working tree is dirty, ask the user at the interview checkpoint (branch base / commit-stash-proceed) before proceeding with initialization.

## Resuming

On invocation, if `.ios-orchestrator/state.json` exists, the orchestrator reads it to determine where to pick up. If `last_commit_sha` is set, before continuing it runs `git rev-parse HEAD` in `target_project_path` (on whichever branch is currently checked out) and compares it to `last_commit_sha`. (For pre-0.3.0 `new_app` runs that had not yet reached `pr_creation`, `last_commit_sha` is unset, so this drift check is skipped. Under the v0.3.0 git model, `last_commit_sha` is set at initialization and always present.)

- **Match (or drift check skipped)**: proceed from `phase`/`phase_status` as recorded (if `phase_status: "complete"`, advance to the next phase in sequence; if `"in_progress"`, re-dispatch that phase using the original inputs, including `interview_output`/`architecture_summary` from `state.json` for the Architect — and `design_sources`, if set, so a resumed Architect can map them at graph creation per `design-mode.md`). For runs with a `task_graph`: tasks recorded `in_progress` reset to `pending` and re-dispatch fresh — the dispatched agent is instructed to inspect its `owned_files` for partial prior work first; tasks recorded `complete` are never re-run.
- **Mismatch**: flag the drift to the user — show `last_commit_sha`, the current HEAD, and a one-line `git log` of the commits in between — and ask via `AskUserQuestion` whether to: proceed anyway (treating the new commits as part of this run's work), re-run the current phase from scratch, or have the Architect re-scope first (jumps back to the `architect` phase).
