# Orchestration Flow

This is the phase sequence the orchestrator follows once it has determined the mode (`new_app` or `feature_addition`) and initialized/loaded `state.json` (see `state-schema.md`). After every phase, run the full checkpoint procedure in `checkpoints.md` (which includes the scope check from `role-boundaries.md`) before moving to the next phase.

## Step 0 (both modes): Orchestrator interview

The orchestrator (running in the user's main session) invokes the `superpowers:brainstorming` skill itself to interview the user about what's being built/changed:

- Follow the brainstorming skill through design approval: explore project context, optionally offer the visual companion (not expected in this CLI-driven context and can be left declined/skipped), ask clarifying questions one at a time, propose 2-3 approaches with trade-offs, then present the design in sections until the user approves it.
- **Adapted terminal steps**: once the design is approved, do NOT write a spec document to `docs/superpowers/specs/`, run a spec-review loop, ask the user to review a written spec, or invoke `writing-plans` - this orchestration flow IS the implementation plan, so skip all of brainstorming's remaining post-approval checklist items.
- The approved interview output (requirements, chosen approach, design summary) becomes `interview_output`, persisted to `state.json` at initialization (see `state-schema.md`) and passed to the Architect in step 1.
- For `feature_addition` against an existing project with no state file (see "Existing non-orchestrator project" below), do this interview *before* initializing `state.json`, so the Architect's first dispatch can include both `interview_output` and the codebase-survey instruction.

## New app
(target path doesn't exist, or exists but has no `.ios-orchestrator/state.json`, and is otherwise empty/non-project)

If `target_project_path` exists, is non-empty, and contains no recognizable Xcode/SPM project (i.e. doesn't match "Existing non-orchestrator project" below), confirm with the user via `AskUserQuestion` before proceeding as `new_app` - the directory may contain unrelated files that the Developer's scaffolding could conflict with.

1. **architect**: dispatch `ios-architect` with `mode: new_app`, `target_project_path`, `interview_output`. It writes `docs/architecture.md` and reports `screens_affected`. Checkpoint.
2. **ui_designer**: if `screens_affected: true`, ask the design-mode question (`design-mode.md`) if not yet answered, then dispatch `ios-ui-designer` with `target_project_path`, `architecture_summary` (contents of `docs/architecture.md`), `design_mode`, `design_sources`. It writes `docs/design.md`. Checkpoint. If `screens_affected: false`, skip to step 3.
3. **developer (implement)**: dispatch `ios-developer` with `dispatch_type: implement`, `mode: new_app`, `target_project_path`, `architecture_summary`, `design_summary` (if step 2 ran). It scaffolds the project and builds until it compiles. Checkpoint.
4. **test_engineer**: dispatch `ios-test-engineer` with `dispatch_type: test`, `mode: new_app`, `target_project_path`, `architecture_summary`, `design_summary` (if applicable), `developer_summary` (from step 3's report). It writes tests and runs them until passing. Checkpoint.
5. **pr_creation**: see `pr-review-flow.md` (`branch_name: "feature/initial-implementation"`, including the no-GitHub-remote checkpoint if needed). Checkpoint.
6. **code_review**: see `pr-review-flow.md`'s review loop. Checkpoint.
7. **merge**: see `pr-review-flow.md`. Checkpoint.
8. **release_manager**: dispatch `ios-release-manager` with `target_project_path`, `architecture_summary`, `design_summary` (if applicable). It writes `docs/release-checklist.md`. Checkpoint. (This is the final phase - after this checkpoint, the run is complete.)

## Feature addition
(`.ios-orchestrator/state.json` exists, OR the project exists with no state file - see "Existing non-orchestrator project" below)

1. **architect**: dispatch `ios-architect` with `mode: feature_addition`, `target_project_path`, `interview_output`. It does a codebase survey and returns a scope summary (no file written) plus `screens_affected`. Checkpoint persists the scope summary as `architecture_summary` in `state.json` (see `checkpoints.md`), since no file is written and the Architect has no memory.
2. **ui_designer**: only if `screens_affected: true` - same as new app step 2, but `architecture_summary` is `state.json`'s persisted scope summary text (not a file). Otherwise skip to step 3.
3. **developer (implement)**: dispatch `ios-developer` with `dispatch_type: implement`, `mode: feature_addition`, `target_project_path`, `architecture_summary` (scope summary text), `design_summary` (if step 2 ran). Checkpoint.
4. **test_engineer**: same as new app step 4, with `mode: feature_addition`. Checkpoint.
5. **pr_creation**: see `pr-review-flow.md` (`branch_name: "feature/<slug>"`, slug derived from the change description). Checkpoint.
6. **code_review**: see `pr-review-flow.md`'s review loop. Checkpoint.
7. **merge**: see `pr-review-flow.md`. Checkpoint.
8. **release_manager**: skipped unless the user explicitly requests a release-readiness pass (if requested, dispatch as in new app step 8). This is the final phase either way - after step 7's checkpoint (or step 8's, if run), the run is complete.

## Existing non-orchestrator project

If `target_project_path` exists, contains an Xcode/SPM project, but has no `.ios-orchestrator/state.json`: treat as `feature_addition`, first run. After the orchestrator interview (step 0), initialize `state.json` (per `state-schema.md`'s Initialization section) before dispatching the Architect, and instruct the Architect (in its dispatch prompt) to do a quick codebase survey (it does this automatically per `agents/ios-architect.md`).

## Resuming

See `state-schema.md`'s Resuming section for the drift-detection procedure. Once resumed, continue the sequence above from the recorded `phase`/`phase_status`.
