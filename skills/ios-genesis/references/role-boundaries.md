# Role Boundaries & Scope Discipline

Each subagent's own prompt (`agents/*.md`) includes its role boundaries. This doc covers the orchestrator-side scope check that runs as part of every checkpoint (see `checkpoints.md`, step 2).

## Role summary

| Agent | In scope | Out of scope |
|---|---|---|
| ios-architect | Requirements, architecture decisions, module breakdown; `docs/architecture.md` or scope summary | Specific screen layouts (UI Designer's job); Swift/test code |
| ios-ui-designer | Screen list, navigation, view hierarchy, component breakdown; `docs/design.md` (+ mockups per design mode) | Architecture decisions in `docs/architecture.md`; Swift implementation code |
| ios-developer | Implementation code, project scaffolding, builds, branches/commits/PRs | Redefining architecture or screen designs (raise as `open_risks` instead); test code |
| ios-test-engineer | Test code, running tests | App/source code (raise apparent app bugs as `open_risks`) |
| ios-code-reviewer | PR review comments and approval | Pushing code changes itself - fixes go through Developer/Test Engineer |
| ios-release-manager | Versioning, Info.plist, asset catalog checklist, `docs/release-checklist.md` | App logic, views, tests |

## Scope check

After each phase, before presenting the checkpoint summary, the orchestrator checks which files changed and compares them against that phase's expected path patterns (table below).

**`state.json` is exempt from this check in every phase** - the orchestrator updates `.ios-orchestrator/state.json` after every phase as part of normal bookkeeping, so its presence in a diff is never flagged.

For `bring_your_own` design mode, the files the UI Designer *reads* (per `design_sources`) are inputs, not outputs, and are never flagged regardless of where they live (even if a `design_sources` path happens to be inside the project directory).

### How to check

Whether the orchestrator uses `git status --porcelain` (uncommitted changes) or a diff against `last_commit_sha` (committed changes) depends on whether the phase commits its own work:

- **architect, ui_designer, test_engineer, release_manager**: these phases don't commit - run `git status --porcelain` in `target_project_path` and check the listed files.
- **developer, pr_creation**: the Developer commits and pushes as part of these phases, so `git status --porcelain` may be clean - run `git diff --name-only <last_commit_sha> HEAD` instead, then update `last_commit_sha` to the new HEAD (per `state-schema.md` / `checkpoints.md` step 1).
- **code_review, merge**: no local file changes expected from either - skip the scope check entirely. (`merge`'s `gh pr merge` changes the remote default branch, but that's the intended outcome, not a violation.)

### Expected paths per phase

| Phase | Expected paths |
|---|---|
| architect | `docs/architecture.md` |
| ui_designer | `docs/design.md` (Figma/Claude Design mockups are external, not local files) |
| developer | Source/project files (`*.swift`, `Package.swift`, `*.xcodeproj`/`*.xcworkspace`, asset catalogs) - not `docs/architecture.md` or `docs/design.md` |
| test_engineer | Test target files (`*Tests.swift` or equivalent) |
| pr_creation | Same as `developer` (branch/commit/push only - no new file changes beyond what the `developer` phase already produced) |
| release_manager | `docs/release-checklist.md`, `Info.plist`, versioning/project settings, app icon assets |

### Violations

Any changed file outside the expected patterns for that phase is **not reverted automatically** - add an `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional") as part of `checkpoints.md` step 1, so it's surfaced at the checkpoint for the user to accept or ask the agent to undo.
