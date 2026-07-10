# Role Boundaries & Scope Discipline

Each subagent's own prompt (`agents/*.md`) includes its role boundaries. This doc covers the orchestrator-side scope check that runs as part of every checkpoint (see `checkpoints.md`, step 2).

## Role summary

| Agent | In scope | Out of scope |
|---|---|---|
| ios-architect | Requirements, architecture decisions, module breakdown; `docs/architecture.md` or scope summary | Specific screen layouts (UI Designer's job); Swift/test code |
| ios-ui-designer | Screen list, navigation, view hierarchy, component breakdown; `docs/design.md` (+ mockups per design mode) | Architecture decisions in `docs/architecture.md`; Swift implementation code |
| ios-developer | Implementation code, project scaffolding, builds, branches/commits/PRs | Redefining architecture or screen designs (raise as `open_risks` instead); test code |
| ios-test-engineer | Test code, running tests | App/source code (raise apparent app bugs as `open_risks`) |
| ios-visual-verifier | Simulator build/install/launch, screenshots, structural comparison against the design reference | Editing any source/project file; committing; fixing findings (those go through the Developer) |
| ios-code-reviewer | PR review comments and approval | Pushing code changes itself - fixes go through Developer/Test Engineer |
| ios-release-manager | Reading versioning/Info.plist/asset catalog info to write `docs/release-checklist.md` | App logic, views, tests, and editing `Info.plist`/project settings/asset catalogs directly (those are read-only inputs; gaps become action items in the checklist) |

## Scope check

After each phase, before presenting the checkpoint summary, the orchestrator checks which files changed and compares them against that phase's expected path patterns (table below).

**The `.ios-orchestrator/` directory is exempt from this check in every phase** - the orchestrator updates `.ios-orchestrator/state.json` after every phase, and the Visual Verifier writes screenshots under `.ios-orchestrator/screenshots/`, as normal bookkeeping; their presence in a diff is never flagged. The same exemption covers the orchestrator's one-time initialization append of `.ios-orchestrator/` to the repo's `.gitignore` for `feature_addition` (see `state-schema.md`'s Initialization) - an uncommitted `.gitignore` change consisting of that append is bookkeeping, not an agent scope violation.

For `bring_your_own` design mode, the files the UI Designer *reads* (per `design_sources`) are inputs, not outputs, and are never flagged regardless of where they live (even if a `design_sources` path happens to be inside the project directory).

### How to check

Every phase has a git baseline — the repo and working branch exist from initialization (see `state-schema.md`'s Initialization). The scope check runs for every phase; there are no skip-if-no-repo carve-outs.

The method depends on whether the phase fans out across multiple tasks:

- **Sequential phases and single-task graphs** (architect, ui_designer, pr_creation, release_manager; also developer/visual_verification/test_engineer when the graph has exactly one task): run `git status --porcelain` in `target_project_path` immediately **before** the checkpoint's `wip(<phase>)` commit, and compare the listed paths against the expected patterns below.
- **Fanned-out phases** (developer, visual_verification, test_engineer on multi-task graphs): at each wave-end, run `git diff --name-only <previous wip commit>` in `target_project_path` and attribute each path to a task by matching against that task's `owned_files` prefixes. Paths matching no task's prefix are unattributable — add an `open_risks` entry (Violations section).
- **code_review, merge**: no local file changes expected from either - skip the scope check entirely. (`address_review` commits during `code_review` and `merge`'s `gh pr merge` change HEAD/the remote default branch, but that's the intended outcome, not a violation.)

### Expected paths per phase

| Phase | Expected paths |
|---|---|
| architect | `docs/architecture.md` |
| ui_designer | `docs/design.md` (Figma/Claude Design mockups are external, not local files) |
| developer | Source/project files (`*.swift`, `project.yml`, `Package.swift`, `*.xcodeproj`/`*.xcworkspace`, `Info.plist`, `PrivacyInfo.xcprivacy`, asset catalogs, `.gitignore`) - not `docs/architecture.md` or `docs/design.md`. **Fan-out (multi-task graphs):** each wave task may only touch its `owned_files`; `project.yml` edits are further restricted to the `foundation` and `integration` tasks. |
| visual_verification | None from the verifier itself (screenshots live under the exempt `.ios-orchestrator/`); if `address_visual` ran, fix paths must match the `developer` expected patterns for that task's `owned_files`. |
| test_engineer | Test target files (`*Tests.swift` or equivalent), plus `project.yml`/`Package.swift` edits and the regenerated `.xcodeproj` when registering a newly created test target (either mode - a `feature_addition` project without UI tests legitimately gains a target too). **Fan-out (multi-task graphs):** each wave task may only touch its `owned_files`; `project.yml` edits are restricted to the serial registration pre-step. |
| pr_creation | None — this phase pushes already-committed changes and opens a PR; `git status --porcelain` is expected to be clean. |
| release_manager | `docs/release-checklist.md` only (reads `Info.plist`, project settings, and asset catalogs as inputs without modifying them, same as the `bring_your_own` `design_sources` carve-out above) |

### Violations

Any changed file outside the expected patterns for that phase is **not reverted automatically** - add an `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional") as part of `checkpoints.md` step 1, so it's surfaced at the checkpoint for the user to accept or ask the agent to undo.
