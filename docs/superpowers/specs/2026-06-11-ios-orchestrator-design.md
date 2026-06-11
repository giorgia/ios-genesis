# iOS Orchestrator — Design

## Overview

A Claude Code toolkit for building and extending iOS apps using a coordinated team of specialist subagents. The toolkit lives in this repo (`iOSOrchestator`) and is applied to *other* project directories — it does not host iOS app code itself.

A single skill, `/build-ios-app`, acts as the orchestrator: it runs in the user's main Claude Code session, dispatches specialist subagents in sequence, checkpoints with the user after each phase, and coordinates a GitHub PR review loop between the developer and reviewer.

## Architecture & File Layout

```
iOSOrchestator/
└── .claude/
    ├── agents/
    │   ├── ios-architect.md
    │   ├── ios-ui-designer.md
    │   ├── ios-developer.md
    │   ├── ios-test-engineer.md
    │   ├── ios-code-reviewer.md
    │   └── ios-release-manager.md
    └── skills/
        └── build-ios-app/
            └── SKILL.md
```

`/build-ios-app <target-project-path> <description>` is the entry point. The orchestrator:

1. Checks whether `<target-project-path>` already contains a project and/or `.ios-orchestrator/state.md`.
2. Routes to the **new app** flow or the **feature addition** flow accordingly.
3. Dispatches subagents via the Agent tool, one phase at a time, pausing for user checkpoints between phases.

State for resumability lives in the target project at `<target-project>/.ios-orchestrator/state.md`, not in this repo — each app's orchestration history travels with the app.

## Subagent Roster

| Agent | Model | Responsibility | Key tools |
|---|---|---|---|
| **ios-architect** | Sonnet | New app: turns a description into requirements + architecture (modules, data flow, frameworks), writes `docs/architecture.md`. Feature addition: scopes the change, identifies affected modules/files, asks clarifying questions before writing the spec if requirements are ambiguous. | Read, Grep, Glob, Write |
| **ios-ui-designer** | Sonnet | Defines screen list, navigation flow, and SwiftUI view hierarchy per screen (component breakdown, state, HIG considerations). Writes `docs/design.md`. Skipped for feature additions unless new/changed screens are needed. | Read, Write |
| **ios-developer** | Sonnet | Scaffolds the Xcode project (new) or modifies the existing one. Implements views/models/services per the design. Runs `xcodebuild build` / `swift build` until it compiles. Creates feature branches, commits, pushes, and opens PRs. Addresses reviewer feedback. | Read, Write, Edit, Bash |
| **ios-test-engineer** | Sonnet | Writes/updates unit and UI tests for new or changed functionality. Runs `xcodebuild test` until passing. Re-runs tests after reviewer-driven fixes if behavior changed. | Read, Write, Edit, Bash |
| **ios-code-reviewer** | Sonnet | Reviews the PR via `gh pr diff`/`gh pr view`, posts comments via `gh pr review`/`gh pr comment`. Approves via `gh pr review --approve` once satisfied. | Read, Grep, Glob, Bash |
| **ios-release-manager** | Haiku | New app only (or on request): versioning, Info.plist setup, app icon/asset catalog checklist, App Store readiness notes. Writes `docs/release-checklist.md`. | Read, Write, Edit |

The orchestrator (the skill, run in the user's main session) inherits the session's model.

## Orchestration Flow

### New app
(target path doesn't exist, or exists but has no `.ios-orchestrator/state.md`)

1. **Architect** — requirements + architecture → `docs/architecture.md` → checkpoint
2. **UI Designer** — screens, navigation, view hierarchy → `docs/design.md` → checkpoint
3. **Developer** — scaffolds Xcode project, implements per design, runs `xcodebuild build`/`swift build` until it compiles → checkpoint
4. **Test Engineer** — writes unit/UI tests, runs `xcodebuild test` until passing → checkpoint
5. **PR creation** — Developer commits to a feature branch (e.g. `feature/initial-implementation`), pushes, and opens a PR describing the build, referencing `docs/architecture.md`/`docs/design.md`.
   - If no GitHub remote exists: orchestrator checkpoints with the user — create a GitHub repo (public/private)? If yes, `gh repo create`, then push and open PR.
6. **Code Reviewer** — reviews the PR; loops with Developer (and Test Engineer if behavior changes) until approved or max rounds reached → checkpoint
7. **Auto-merge** — once approved, orchestrator runs `gh pr merge` (squash)
8. **Release Manager** — versioning, Info.plist, icon/asset checklist → `docs/release-checklist.md` → checkpoint

### Feature addition
(state file exists, or project exists but has no state file — orchestrator initializes one and has the Architect do a quick codebase survey first)

1. **Architect** — scopes the change, identifies affected modules/files → checkpoint
2. **UI Designer** — only if the architect's scope requires new/changed screens; otherwise skipped
3. **Developer** — implements, builds → checkpoint
4. **Test Engineer** — updates/adds tests, runs → checkpoint
5. **PR creation** — Developer creates a feature branch off the project's default branch, commits, pushes, opens a PR
6. **Code Reviewer** — reviews the PR; loops with Developer (and Test Engineer) until approved or max rounds reached → checkpoint
7. **Auto-merge** — once approved, orchestrator runs `gh pr merge` (squash)
8. **Release Manager** — skipped unless the user explicitly requests a release-readiness pass

## PR-Based Review Flow

- Requires the `gh` CLI to be authenticated. The orchestrator checks this upfront and surfaces a clear message if not.
- The Code Reviewer reviews via `gh pr diff`/`gh pr view` and posts comments via `gh pr review`/`gh pr comment`.
- If issues are found, the Developer addresses them, commits, and pushes (updating the PR in place). If the fix affects tested behavior, the Test Engineer re-runs tests.
- The loop (Reviewer → Developer → [Test Engineer] → Reviewer) continues for up to **2 rounds**. If issues remain unresolved after that, the orchestrator surfaces them to the user instead of looping further.
- Once the Reviewer approves, the orchestrator runs `gh pr merge` automatically (squash merge).

## State File

`<project>/.ios-orchestrator/state.md`, written and updated by the orchestrator (not the subagents) after each phase completes. Records:

- Current phase and timestamp
- Brief summary of what each agent produced
- Links to docs each agent wrote (`docs/architecture.md`, `docs/design.md`, `docs/release-checklist.md`)
- PR number/URL once opened

On resume, the orchestrator reads this file to determine where to pick up and re-confirms with the user before continuing, since project state may have changed since the last session.

## Error Handling & Edge Cases

- **Build/test failures**: Developer/Test Engineer retry fixes themselves (build → fix → rebuild) up to ~3 attempts before surfacing the failure to the user with the error output.
- **Code review loop**: capped at 2 rounds (see PR-Based Review Flow above); unresolved issues after that are surfaced to the user.
- **Ambiguous requirements**: the Architect asks the user clarifying questions (via AskUserQuestion) before writing `docs/architecture.md`, rather than guessing.
- **Resuming with drift**: if `.ios-orchestrator/state.md` exists but the project has changed since (e.g., commits after the last recorded phase), the orchestrator flags this and asks whether to proceed, re-run the affected phase, or have the Architect re-scope first.
- **Existing non-orchestrator project**: if the target path has an Xcode project but no state file, treat it as "feature addition, first run" — initialize a state file and have the Architect do a quick codebase survey before scoping the change.
- **No GitHub remote (new app)**: orchestrator checkpoints with the user before creating a repo via `gh repo create`.
- **`gh` CLI not authenticated**: orchestrator surfaces this to the user before reaching the PR creation step.

## Validation

No traditional unit test suite applies, since this project produces agent/skill *definitions* (markdown + prompts). Validation is a real end-to-end dry run: after writing the agents and skill, run `/build-ios-app` against a small throwaway app spec (e.g., a simple single-screen counter app) in a scratch directory, and confirm each phase runs, produces the expected docs, the PR review loop functions, and the final app builds and passes tests.
