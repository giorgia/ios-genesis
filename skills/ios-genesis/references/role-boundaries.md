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

If `target_project_path` doesn't exist yet, or exists but isn't a git repository yet, skip the scope check entirely for that phase - there's no git history to check against. This is expected for `new_app`'s `architect`, `ui_designer`, and `developer` (`implement`) phases, since the repo isn't created until `pr_creation`'s `git init` (see `agents/ios-developer.md`).

Otherwise, whether the orchestrator uses `git status --porcelain` (uncommitted changes) or a diff against `last_commit_sha` (committed changes) depends on whether the phase commits its own work:

- **architect, ui_designer, developer, test_engineer, release_manager**: none of these phases commit (the Developer's `implement` dispatch explicitly does not commit/push) - run `git status --porcelain` in `target_project_path` and check the listed files.
- **visual_verification**: the Developer's `implement` changes are still uncommitted at this point (commits happen at `pr_creation`), so a plain `git status --porcelain` is expected to be non-empty and is NOT the check. Instead the check is **delta-based**: capture `git status --porcelain` immediately before the first verifier dispatch and compare against `git status --porcelain` after the loop concludes. Zero new/changed paths if no fix round ran; new/changed paths matching the `developer` expected patterns if `address_visual` ran; anything else is a violation (standard `open_risks` treatment).
- **pr_creation**: the Developer commits and pushes as part of this phase (including, for `new_app`, the one-time `git init` + initial commit), so `git status --porcelain` may be clean. If `last_commit_sha` was set beforehand (always true for `feature_addition`), run `git diff --name-only <last_commit_sha> HEAD` using that **pre-checkpoint** value (capture it before `checkpoints.md` step 1 overwrites it). If `last_commit_sha` was unset beforehand (`new_app`, since the repo didn't exist before this phase), instead run `git show --name-only --pretty=format: HEAD` to list every file in the new repo's history up to `HEAD`. Either way, let step 1 update `last_commit_sha` to the new HEAD as usual.
- **code_review, merge**: no local file changes expected from either - skip the scope check entirely. (`address_review` commits during `code_review` and `merge`'s `gh pr merge` change HEAD/the remote default branch, but that's the intended outcome, not a violation.)

### Expected paths per phase

| Phase | Expected paths |
|---|---|
| architect | `docs/architecture.md` |
| ui_designer | `docs/design.md` (Figma/Claude Design mockups are external, not local files) |
| developer | Source/project files (`*.swift`, `project.yml`, `Package.swift`, `*.xcodeproj`/`*.xcworkspace`, `Info.plist`, `PrivacyInfo.xcprivacy`, asset catalogs, `.gitignore`) - not `docs/architecture.md` or `docs/design.md` |
| visual_verification | None from the verifier itself (screenshots live under the exempt `.ios-orchestrator/`); if `address_visual` ran, same as `developer` - checked via the delta procedure above |
| test_engineer | Test target files (`*Tests.swift` or equivalent), plus `project.yml`/`Package.swift` edits and the regenerated `.xcodeproj` when registering a newly created test target (either mode - a `feature_addition` project without UI tests legitimately gains a target too) |
| pr_creation | Same as `developer` (branch/commit/push only - no new file changes beyond what the `developer` phase already produced) |
| release_manager | `docs/release-checklist.md` only (reads `Info.plist`, project settings, and asset catalogs as inputs without modifying them, same as the `bring_your_own` `design_sources` carve-out above) |

### Violations

Any changed file outside the expected patterns for that phase is **not reverted automatically** - add an `open_risks` entry (e.g. "Developer modified `docs/architecture.md` - review whether this was intentional") as part of `checkpoints.md` step 1, so it's surfaced at the checkpoint for the user to accept or ask the agent to undo.
