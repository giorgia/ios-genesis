# ios-genesis v0.3.0 — Live Task Board and Phase Fan-Out: Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give ios-genesis a live per-task progress board (Claude Code native task tools) and parallel specialist execution within phases, per the approved spec.

**Architecture:** A `task_graph` in `state.json` (emitted by the Architect, validated/persisted by the orchestrator) drives both wave-parallel dispatch inside phases and a live task board. Writing is parallel; **building is a serial orchestrator-run integration step** at wave end. A new init-time git model (repo + working branch + ignore-first at state initialization) gives every phase a commit baseline in both modes.

**Tech Stack:** The plugin's source is English — markdown skill references and agent prompts. "Tests" here are verification greps and JSON validity checks; the real test is the manual validation protocol (Task 15).

**Spec:** `docs/superpowers/specs/2026-07-09-task-board-and-phase-fanout-design.md` — the spec is the authority; where this plan compresses, the spec's wording wins.

**Working conventions for every task below:**
- Work in this worktree (`.worktrees/task-board-phase-fanout`, branch `feature/task-board-phase-fanout`).
- Commit after each task with `git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit` (no Co-Authored-By trailer).
- After each file edit, re-read the edited section in full — these docs are executed by an LLM, so a dangling half-sentence is a runtime bug.
- Do not renumber or rewrite unrelated sections; keep diffs minimal.

---

## Chunk 1: State schema, git model, scope checks, checkpoints

### Task 1: `task_graph` and the git model in state-schema.md

**Files:**
- Modify: `skills/ios-genesis/references/state-schema.md`

- [ ] **Step 1: Add the `task_graph` field definition.** Insert after the `app_scheme` bullet a new top-level field bullet. **JSON handling:** extend the file's existing full top-level `state.json` example with the `task_graph` key (so the example stays standalone-valid JSON and Step 3's parse check passes); do NOT paste the spec's bare `"task_graph": {...}` fragment as its own fenced block unless wrapped in `{ }`. Content (from spec §1):
  - `task_graph`: object with `cap` (int, default 3) and `tasks` (list). Per task: `id` ("T1"…), `title`, `kind` (`foundation` | `screen` | `feature` | `integration` — cardinality: 0-or-1 foundation, 0-or-1 integration), `owned_files` (exclusive literal directory prefixes or single file paths; disjointness = no owned path is a path-prefix of another task's), `depends_on` (task ids; must form a DAG), `ui_impact` (bool; `screen` always true), `status` (`pending` | `in_progress` | `complete` | `failed` | `dropped`), `results` (accumulates `design_status`, `design_reference`, `build_status`, `verify_status`, `verification_round`, `tests_status`).
  - Single-task graphs: execution degenerates to the sequential v0.2.0 flow and the top-level `verification_round`/`review_round` keep their existing meaning. Multi-task graphs: round counters live in each task's `results`. A state file with **no** `task_graph` (pre-0.3.0) resumes with the legacy sequential flow **including the legacy git model** (see Step 2).
  - Written by the orchestrator only, after validating the Architect-reported graph (disjointness + DAG; on failure re-dispatch the Architect with the defect named, max 2, then surface at the checkpoint).

- [ ] **Step 2: Rewrite the git-model prose.** Update the `last_commit_sha` bullet and the Initialization section:
  - Initialization (post-interview, both modes): `git init` if no repo; **first act: ensure `.gitignore` contains `.ios-orchestrator/`** (create the file for `new_app`; this replaces the feature_addition-only append carve-out — the scope-check exemption for this edit remains); initial commit on the default branch if the repo is empty; create and switch to the working branch (`feature/initial-implementation` for new_app, `feature/<slug>` otherwise; if taken, suffix `-2`). feature_addition edges: checkout on a non-default branch or a dirty working tree → ask the user at the interview checkpoint (branch base / commit-stash-proceed) before initializing.
  - `last_commit_sha`: updated at **every orchestrator commit** (each `wip(<phase>)` checkpoint commit and each `wip(<phase>/wave-N)` commit); drift check on resume unchanged (`git rev-parse HEAD` vs the field).
  - All run commits land on the working branch until `merge`; post-merge phases (`release_manager`) commit to the default branch.
  - **Resuming section** (edit it explicitly): tasks recorded `in_progress` reset to `pending` and re-dispatch fresh (agent inspects its `owned_files` for partial work first); `complete` tasks never re-run. Fix the now-stale parenthetical "For `new_app` runs that haven't reached `pr_creation` yet, `last_commit_sha` is unset, so this drift check is skipped" — under the new model that applies only to legacy (pre-0.3.0) resumes.

- [ ] **Step 3: Verify.** Run: `grep -c "task_graph\|owned_files\|working branch" skills/ios-genesis/references/state-schema.md` — expect ≥ 8. Run: `python3 -c "import json,re,sys; t=open('skills/ios-genesis/references/state-schema.md').read(); [json.loads(m) for m in re.findall(r'\x60\x60\x60json\n(.*?)\x60\x60\x60', t, re.S)]"` — expect exit 0 (all JSON examples parse). Re-read the full file top to bottom for coherence.

- [ ] **Step 4: Commit.** `git add -A && git commit -m "state-schema: task_graph, init-time git model, per-commit last_commit_sha"`

### Task 2: Slim `pr_creation` in pr-review-flow.md

**Files:**
- Modify: `skills/ios-genesis/references/pr-review-flow.md`

- [ ] **Step 1: Edit the pr_creation section.** Remove `git init` and branch-creation responsibilities (both now happen at state initialization per `state-schema.md`). `pr_creation` keeps: `gh auth status` prerequisite, remote setup (including the existing new_app/feature_addition "create a GitHub repo?" `AskUserQuestion` when no remote exists), push of the working branch, PR opening, `pr_url`/`last_commit_sha` state updates, scope check.
- [ ] **Step 2: Add the legacy paragraph.** One paragraph: for pre-0.3.0 state files (no `task_graph`), `pr_creation` retains its old responsibilities — a mid-pipeline `new_app` resume from v0.2.0 has no repo yet, so the legacy `git init` + branch path applies to that case only.
- [ ] **Step 3: Verify.** `grep -n "git init" skills/ios-genesis/references/pr-review-flow.md` — expect exactly one hit, inside the legacy paragraph (note: today's file has zero occurrences — the runtime `git init` lives in `agents/ios-developer.md`'s `create_pr` dispatch, which Task 11 edits; this task only fixes the orchestrator-side contract). Re-read the file.
- [ ] **Step 4: Commit.** `git commit -am "pr-review-flow: branch/init move to state initialization; legacy path for pre-0.3.0 resumes"`

### Task 3: Rework "How to check" in role-boundaries.md

**Files:**
- Modify: `skills/ios-genesis/references/role-boundaries.md`

- [ ] **Step 1: Replace the git-check method section.** Every phase now has a commit baseline (init-time git model). New unified method: sequential phases → `git status --porcelain` against the working tree **before** the checkpoint's wip commit; fanned-out phases → `git diff --name-only <previous wip commit>` attributed to tasks by owned-path prefix; unattributable paths → out-of-pattern `open_risks` entry, as today. Delete the "new_app has no repo yet, skip" carve-outs (visual_verification scope check now runs for new_app too). Keep the init-time `.gitignore` exemption.
- [ ] **Step 2: Add the ownership row.** In the role summary table / expected-path patterns: fanned-out developer/test tasks may only touch their `owned_files` (plus, for the registration pre-step and foundation/integration tasks, `project.yml`).
- [ ] **Step 3: Verify.** `grep -n "isn't a git repository\|no repo" skills/ios-genesis/references/role-boundaries.md` — expect 0 hits (the `code_review`/`merge` "skip the scope check" line is unrelated and stays). Re-read the file.
- [ ] **Step 4: Commit.** `git commit -am "role-boundaries: diff-vs-wip-commit scope checks, ownership attribution"`

### Task 4: Wave-aware checkpoints in checkpoints.md

**Files:**
- Modify: `skills/ios-genesis/references/checkpoints.md`

- [ ] **Step 1: Reorder the checkpoint procedure.** New order: (1) update `state.json` phase/status + per-task `results`; (2) run the scope check (per role-boundaries.md — before any commit); (3) resolve failures (see Step 2); (4) `wip(<phase>): <one-liner>` commit as the **last state-mutating act** (the summary presentation in step 5 follows it), skipped when nothing to commit (`code_review`, `merge`, clean verification passes) — update `last_commit_sha`; (5) present the summary and options.
- [ ] **Step 2: Add the fan-out subsections** (multi-task graphs only; single-task graphs keep the v0.2.0 checkpoint verbatim):
  - **Per-task results table** in the summary: one line per task in the phase's projection — ✓ / ✗ / skipped + one-liner.
  - **Failure handling:** siblings always run to completion; per failed task the options are **retry** (re-dispatch with sibling summaries as context; re-enters the wave scheduler, so the checkpoint legitimately fires again after remaining waves — the one-gate invariant is per *pass*), **drop**, or **stop**. **Drop semantics (verbatim from spec §4):** revert the task's `owned_files` to the last wip commit (checkout tracked paths, delete untracked), exclude the task from all subsequent phase projections, dependents treat it as satisfied, append the `open_risks` entry. Warn explicitly before accepting a drop whose task still has dependents in later projections (dropping `foundation` orphans everything; dropping `integration` ships unwired screens). Wip commits happen only once every failed task is resolved — they are always buildable.
  - **Wave preview:** each post-phase checkpoint previews the next phase's wave plan — projection, dependencies, cap, wave count (e.g. "developer: 8 tasks, cap 3 → foundation, then 3+3+1, then integration"). Options gain "Continue with different cap". The post-architect checkpoint additionally renders the whole graph with `ui_impact` flags for user correction.
  - **Risk-description rule** (v0.2.0 finding #4 text) is unchanged — keep it.
- [ ] **Step 3: Verify.** `grep -c "wave\|drop\|retry" skills/ios-genesis/references/checkpoints.md` — expect ≥ 10. `grep -n "last act" skills/ios-genesis/references/checkpoints.md` — expect 1 hit. Re-read the file.
- [ ] **Step 4: Commit.** `git commit -am "checkpoints: scope-check-before-commit, per-task results, failure/drop semantics, wave preview"`

## Chunk 2: Orchestration flow, task board, design modes, SKILL.md

### Task 5: New reference — task-board.md

**Files:**
- Create: `skills/ios-genesis/references/task-board.md`

- [ ] **Step 1: Write the file.** Contents (concise, ~60 lines): the board is presentation-only; `state.json` is the single source of truth; skip all board calls if the harness lacks the task tools (execution unaffected). Protocol:
  - At graph acceptance: `TaskCreate` one entry per pipeline task (`subject` = task title, `description` = kind + owned_files + phase participation); `TaskUpdate` `addBlockedBy` mirroring `depends_on`.
  - Single-task graphs: create one entry per *phase* instead (architect → … → merge) so sequential runs are visual too.
  - On dispatch: `TaskUpdate status: in_progress`, `activeForm` = "<agent> · <doing what>" (e.g. "ios-developer #2 · building Settings screen").
  - On report: `completed`; on failure keep `in_progress` with the failure noted in the subject until the checkpoint resolves it (retry → re-dispatch; drop → `deleted`; stop → leave as-is).
- [ ] **Step 2: Verify.** `grep -c "TaskCreate\|TaskUpdate" skills/ios-genesis/references/task-board.md` — expect ≥ 4 (name the tools explicitly in the single-task-graph and failure-resolution bullets too). Re-read.
- [ ] **Step 3: Commit.** `git commit -am "task-board: native board protocol reference"`

### Task 6: Fan-out mechanics in orchestration-flow.md

**Files:**
- Modify: `skills/ios-genesis/references/orchestration-flow.md`

This is the largest edit. Keep the existing phase sequence and Step 0 sections; weave fan-out in.

- [ ] **Step 1: Add "Task graph and waves" section** after Step 0, containing (from spec §1/§3):
  - Graph source: Architect report → orchestrator validation (disjointness, DAG; re-dispatch ≤2) → persist → board creation (`task-board.md`).
  - **Phase projection table** (verbatim from spec §3): ui_designer → `ui_impact: true`; developer → all tasks (foundation solo → screens/features in waves → integration solo); visual_verification → `ui_impact: true`; test_engineer → registration pre-step, then foundation + screen + feature; pr_creation/code_review/merge/release_manager → whole-run, no fan-out. Dependency edges evaluate **within the projection**; a dependency with no work in the current phase (or status `dropped`) counts as satisfied.
  - Wave = unblocked projection tasks, ≤ `cap` at a time, dispatched as **concurrent subagent calls in a single message**.
- [ ] **Step 2: Add the design principle + per-phase mechanics** (from spec §3, keeping its wording for the contract-critical sentences):
  - Principle: compilation is an integration act; fan-out agents write, the orchestrator builds serially at wave end.
  - **ui_designer:** one agent per projected task; agents *return* design sections; orchestrator assembles `docs/design.md`. Per-mode: figma → per-task Figma file, link into `results.design_reference`; claude_design → per-task paste summaries concatenated at the checkpoint; bring_your_own → Architect maps `design_sources` entries to tasks at graph creation.
  - **developer:** dispatch includes `owned_files` + no-edits-outside rule (foundation outputs read-only); fan-out agents do not build (at most `swiftc -typecheck` on own files). Wave end: orchestrator runs `xcodegen generate` once + `xcodebuild build` once; errors attributed by ownership → owning agents re-dispatched concurrently with their errors; ≤3 wave-build rounds, then `failed` → checkpoint; unowned errors → integration defect at checkpoint. On success: `wip(<phase>/wave-N)` commit; attribution via `git diff --name-only <previous wip commit>`. Solo waves (foundation, integration, single-task graphs) keep v0.2.0 agent-builds-itself behavior. `project.yml` edits reserved to foundation/integration.
  - **visual_verification:** orchestrator builds once, `simctl install`s the same `.app` per verifier UDID (allocated from `simctl list devices available`; fewer devices than cap → smaller waves — also applies to test runs). Router: foundation owns the `-ios-genesis-screen <Name>` `#if DEBUG` mechanism; integration owns registry entries; launch via `simctl launch <udid> <bundle> -ios-genesis-screen <Name>`; feature_addition without router/integration → root-screen-only + `open_risks`, never a hard failure. 2-round loop per task unchanged; counters per §1 dual-mode rule.
  - **test_engineer:** serial registration pre-step (one dispatch registers targets in `project.yml` + `xcodegen generate`, no siblings); then parallel write-only agents (per-task test directories); wave end: `xcodegen generate` + `xcodebuild build-for-testing` once, then concurrent `xcodebuild test-without-building -only-testing:<task classes> -destination id=<UDID>`; failures route to owning agents, ≤3 rounds; test-file fixes re-enter build-for-testing serially.
- [ ] **Step 3: Reconcile the existing v0.2.0 solo-behavior sentences.** These lines currently contradict fan-out and each needs a "single-task graphs / solo dispatches only" qualifier or an updated sentence pointing at the fan-out section: new_app steps 2 & feature_addition step 2 ("It writes `docs/design.md`" — becomes: solo dispatches write it; fan-out dispatches return sections the orchestrator assembles); new_app step 3 & feature_addition step 3 ("builds until it compiles" — solo only; fan-out agents are write-only); new_app step 5 & feature_addition step 5 ("writes tests and runs them until passing" — solo only). Rewrite the **Visual verification loop** section's dispatch-inputs list to add `simulator_udid`, and for fan-out dispatches `bundle_id`, `screen_name`, and the task's `design_reference`; note `address_visual` fixes re-enter the integration-build rule if several land concurrently; note that in `feature_addition` the router mechanism ships inside the *integration* task when the graph has verifier work (foundation-owns-mechanism is the new_app framing).
- [ ] **Step 4: Update the git-model touchpoints.** Anchor: the file's intro paragraph (which describes mode determination + state init) gains the git-model sentence delegating to `state-schema.md`, and the "Existing non-orchestrator project" section notes the dirty-tree/branch questions; remove the "on `new_app` there is no repo yet and the scope check is skipped" carve-out in the visual verification loop; `pr_creation` references its slimmed contract.
- [ ] **Step 5: Verify.** `grep -c "projection\|wave" skills/ios-genesis/references/orchestration-flow.md` — expect ≥ 15. `grep -n "no repo" skills/ios-genesis/references/orchestration-flow.md` — expect 0 hits outside the legacy/resume note. `grep -n "writes docs/design.md\|builds until it compiles" skills/ios-genesis/references/orchestration-flow.md` — every hit must sit next to a solo/single-task qualifier. Re-read the whole file.
- [ ] **Step 6: Commit.** `git commit -am "orchestration-flow: projections, waves, integration builds, router, git-model touchpoints"`

### Task 7: Per-task design references in design-mode.md

**Files:**
- Modify: `skills/ios-genesis/references/design-mode.md`

- [ ] **Step 1: Edit.** The design-mode question itself is unchanged (asked once per run). Add a fan-out paragraph: in multi-task graphs, mode applies per task — figma yields one file per task (link in `results.design_reference`, superseding the single `design_mode_extra` link flow, which remains for single-task graphs); claude_design and bring_your_own per the orchestration-flow wording. Each verifier receives **its task's** `design_reference`.
- [ ] **Step 2: Verify.** `grep -c "design_reference" skills/ios-genesis/references/design-mode.md` — expect ≥ 2. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "design-mode: per-task references in fan-out"`

### Task 8: SKILL.md — control flow + reference index

**Files:**
- Modify: `skills/ios-genesis/SKILL.md`

- [ ] **Step 1: Edit.** Reference list: add `references/task-board.md` with a one-line description. Top-level control flow: step 2 (state init) notes the git model (init/ignore/branch — delegate to `state-schema.md`); step 4 notes that phases run their projections in waves per `orchestration-flow.md` and that the orchestrator maintains the task board per `task-board.md` throughout. Notes section: add "fan-out dispatches go out as concurrent Agent calls in one message; every dispatch still carries all context the subagent needs" (memoryless rule unchanged).
- [ ] **Step 2: Verify.** `grep -c "task-board" skills/ios-genesis/SKILL.md` — expect ≥ 2. Re-read (file is ~50 lines; keep it under ~70).
- [ ] **Step 3: Commit.** `git commit -am "SKILL: board protocol + wave execution in control flow"`

## Chunk 3: Agent prompts, release chores, validation

### Task 9: ios-architect.md — emit the graph

**Files:**
- Modify: `agents/ios-architect.md`

- [ ] **Step 1: Edit.** Add to the task instructions: decompose into a task graph when the scope has >1 independently buildable unit (screens/features); otherwise emit a single `feature` task. Rules (from spec §1): kinds + cardinality; foundation = shared models/app entry/theme/design-system + router mechanism when any task has `ui_impact`; integration = navigation wiring + router registry, `depends_on` all screens/features; `owned_files` as literal directory prefixes, disjoint; `depends_on` DAG; `ui_impact` per task (screens always true; features when user-visible). bring_your_own: map `design_sources` entries to tasks. Add a `task_graph:` block (the spec's JSON shape) to the report format. Keep `screens_affected` as-is — it still gates whether ui_designer/visual_verification run at all; per-task `ui_impact` refines *which tasks* those phases work on in multi-task graphs. Note the re-dispatch contract: if the orchestrator reports a validation defect (overlap/cycle), fix and re-emit.
- [ ] **Step 2: Verify.** `grep -c "task_graph\|ui_impact\|owned_files" agents/ios-architect.md` — expect ≥ 8. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "ios-architect: task-graph decomposition in report"`

### Task 10: ios-ui-designer.md — report-only sections in fan-out

**Files:**
- Modify: `agents/ios-ui-designer.md`

- [ ] **Step 1: Edit.** Add a dispatch-mode switch: when the dispatch prompt includes `task_id` (fan-out), do NOT write `docs/design.md` — return the design section for that task in the report (new report fields `design_section:` and `design_reference:` — the latter replaces `design_mode_extra` in fan-out reports; the orchestrator stores it into the task's `results.design_reference`); the orchestrator assembles the file. Solo dispatches (no `task_id`) keep the v0.2.0 write-the-file behavior verbatim. The Revisions rule (v0.2.0 finding #3) applies to whichever medium is authoritative — in fan-out, that's the returned section.
- [ ] **Step 2: Verify.** `grep -c "task_id\|design_section" agents/ios-ui-designer.md` — expect ≥ 4. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "ios-ui-designer: report-only sections for fan-out dispatches"`

### Task 11: ios-developer.md — write-only fan-out + integration dispatches

**Files:**
- Modify: `agents/ios-developer.md`

- [ ] **Step 1: Edit.** Add to the `implement` dispatch: when the prompt includes `task_id` + `owned_files` (fan-out), (a) edit only within `owned_files` — everything else, including foundation outputs, is read-only; (b) do **not** run `xcodegen generate` or `xcodebuild` — the orchestrator builds at wave end (at most `swiftc -typecheck` on own files); (c) a follow-up dispatch may deliver attributed compile errors from the integration build — fix within `owned_files` only; (d) the SwiftUI Pro review runs after the `swiftc -typecheck` pass, before reporting — its "rebuild to confirm" step doesn't apply (no build in write-only dispatches). Foundation/integration task dispatches run solo and keep the build-until-compiles loop (SwiftUI Pro review unchanged there); (e) **`create_pr` dispatch:** remove its `git init` + initial-commit + branch-creation responsibilities for 0.3.0 runs (the branch exists since state init; `branch_name` becomes the already-checked-out working branch) — retain them behind an explicit "legacy: pre-0.3.0 state files only" note, mirroring Task 2's pr-review-flow paragraph; update the line-74 `.gitignore` comment that references "create_pr's git init"; integration's job is navigation wiring + router registry; `project.yml` changes are legal only in foundation/integration/registration dispatches. The "report only what exists" rule (v0.2.0 finding #2) is unchanged.
- [ ] **Step 2: Verify.** `grep -c "owned_files\|wave" agents/ios-developer.md` — expect ≥ 6. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "ios-developer: ownership-scoped write-only fan-out, integration dispatch"`

### Task 12: ios-visual-verifier.md — UDID targeting, router, no-build mode

**Files:**
- Modify: `agents/ios-visual-verifier.md`

- [ ] **Step 1: Edit.** (a) Replace `booted` targeting: the dispatch provides `simulator_udid`; all `simctl` calls target it explicitly. (b) Fan-out dispatches (with `task_id`) skip build+install — the orchestrator pre-installs the app; the dispatch provides `bundle_id` and `screen_name`; launch via `xcrun simctl launch <udid> <bundle_id> -ios-genesis-screen <screen_name>`; if the screen isn't reachable (router missing/unregistered), verify the root screen only and report the gap as a risk (never a hard failure). (c) Screenshots: `.ios-orchestrator/screenshots/<task_id>/round-<N>-<screen>.png` (solo dispatches keep the flat v0.2.0 naming). (d) Solo dispatches keep the v0.2.0 build-install-launch flow, but self-selection changes shape: the agent still picks the newest available iPhone, then targets **its UDID explicitly in every subsequent call** (`booted` disappears in both modes; the orchestrator supplies `simulator_udid` only for fan-out dispatches).
- [ ] **Step 2: Verify.** `grep -n "booted" agents/ios-visual-verifier.md` — expect 0 hits (or only inside an "already booted is fine" error note). `grep -c "simulator_udid\|task_id" agents/ios-visual-verifier.md` — expect ≥ 5. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "ios-visual-verifier: explicit UDID, router launch, pre-installed fan-out mode"`

### Task 13: ios-test-engineer.md — registration pre-step + test-without-building

**Files:**
- Modify: `agents/ios-test-engineer.md`

- [ ] **Step 1: Edit.** Three dispatch shapes: (a) **registration** (`dispatch_type: register_targets`): add missing test targets to `project.yml`, run `xcodegen generate`, build nothing else, report; (b) **fan-out write** (`task_id` + `owned_files`): write test files into the task's test directory only; do not build or run — the orchestrator runs `build-for-testing` at wave end; (c) **fix rounds** (discriminator: `task_id` + `failing_test_output` present): fix within owned test files only (≤3 rounds, orchestrator-controlled). The existing `retest` dispatch is unchanged (whole-run). Solo dispatches (single-task graphs) keep the v0.2.0 write→run→fix loop with an explicit `-destination id=<udid>` — the agent self-selects the newest available iPhone and then targets its UDID, mirroring the verifier's Task 12(d) pattern.
- [ ] **Step 2: Verify.** `grep -c "register_targets\|test-without-building\|build-for-testing" agents/ios-test-engineer.md` — expect ≥ 4. Re-read.
- [ ] **Step 3: Commit.** `git commit -am "ios-test-engineer: registration pre-step, write-only fan-out, orchestrated test runs"`

### Task 14: Version bump + README

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`

- [ ] **Step 1: plugin.json.** `version` → `"0.3.0"`; extend `description` with "live task board and parallel wave execution". Validate: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"` — exit 0.
- [ ] **Step 2: README.** Add a "0.3.0 — task board and fan-out" section: the live board, phase fan-out with waves + cap 3, foundation/integration tasks, write-parallel/build-serial principle, the new git model (branch-per-run, wip commits), and the router. One honest paragraph on why builds are serial (shared-target compilation is an integration act). Verify: `grep -c "0.3.0" README.md` — expect ≥ 1.
- [ ] **Step 3: Commit.** `git commit -am "Bump to 0.3.0; document task board and fan-out in README"`

### Task 15: Manual validation (with the user)

**Files:** none (validation — spec "Validation plan", watcher protocol as in v0.2.0)

- [ ] **Step 1: new_app, 3-screen app** (suggested: "Habitat — a 3-screen habit tracker: Today list, Add Habit form, Stats"). Install the plugin from this worktree (`--plugin-dir` smoke test first: skill + 7 agents + board tools). Watch: graph at the post-architect checkpoint (foundation/integration present, `ui_impact` flags, disjoint `owned_files`); init-time git model (working branch exists before architect, `.gitignore` first commit); designer fan-out (sections assembled, no designer writes design.md); developer waves (write-only agents, one `xcodegen generate` + build per wave, error routing on failure); router + integration wiring; verifier fan-out (per-UDID simulators, per-task screenshot dirs, non-root screens reached via `-ios-genesis-screen`); board reflecting every transition; wave preview + cap override at a checkpoint.
- [ ] **Step 2: feature_addition, two parallel features on TipTop** — one is the clipped-Custom-chip fix (`ui_impact: true`), the other non-UI (e.g. "round per-person up to the nearest cent" setting). Watch: two-task graph (no foundation needed — confirm the Architect doesn't invent one), dirty-tree/branch questions at init if applicable, chip fix flows through designer + verifier (the `feature`-kind visual guarantee), wave attribution scope check, PR contains wip-commit history squashed cleanly.
- [ ] **Step 3: Failure + resume drills.** (a) Force a build failure (feature description containing an impossible API constraint) → verify wave-build rounds, `failed` status, checkpoint retry/drop options, drop reverting owned files and later builds staying green. (b) Interrupt mid-wave (Stop during a developer wave) → re-invoke; verify `in_progress` → `pending` reset, completed tasks not re-run, board reconstructed.
- [ ] **Step 4:** File findings, fix, merge PR, re-point marketplace, blog post 7.
