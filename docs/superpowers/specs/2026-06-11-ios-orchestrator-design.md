# iOS Orchestrator — Design

## Overview

A Claude Code toolkit for building and extending iOS apps using a coordinated team of specialist subagents. The toolkit lives in this repo (`iOSOrchestator`) and is applied to *other* project directories — it does not host iOS app code itself.

A single skill, `/ios-genesis`, acts as the orchestrator: it runs in the user's main Claude Code session, dispatches specialist subagents in sequence, checkpoints with the user after each phase, and coordinates a GitHub PR review loop between the developer and reviewer.

The toolkit is packaged as a Claude Code **plugin** (see Packaging & Installation below), so `/ios-genesis` is available from any project directory once installed — the user does not need to run Claude Code from within `iOSOrchestator`.

## Architecture & File Layout

```
iOSOrchestator/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── agents/
│   ├── ios-architect.md
│   ├── ios-ui-designer.md
│   ├── ios-developer.md
│   ├── ios-test-engineer.md
│   ├── ios-code-reviewer.md
│   └── ios-release-manager.md
└── skills/
    └── ios-genesis/
        ├── SKILL.md
        └── references/
```

`/ios-genesis <target-project-path> <description>` is the entry point. The orchestrator:

1. Checks whether `<target-project-path>` already contains a project and/or `.ios-orchestrator/state.json`.
2. Routes to the **new app** flow or the **feature addition** flow accordingly.
3. Dispatches subagents via the Agent tool, one phase at a time, pausing for user checkpoints between phases.

State for resumability lives in the target project at `<target-project>/.ios-orchestrator/state.json`, not in this repo — each app's orchestration history travels with the app.

## Packaging & Installation

This repo doubles as a local Claude Code plugin marketplace (`.claude-plugin/marketplace.json`) containing one plugin, `ios-genesis` (`.claude-plugin/plugin.json`), whose `agents/` and `skills/` directories are this repo's `agents/` and `skills/` directories. It is **not published** to any public marketplace.

To install locally:

```
/plugin marketplace add /Users/giorgiamarenda/Projects/iOSOrchestator
/plugin install ios-genesis@ios-orchestrator
```

After installation, `/ios-genesis <target-project-path> <description>` and the six `ios-*` subagents are available in any Claude Code session, regardless of working directory. Re-running `/plugin marketplace add` after pulling changes to this repo picks up updates to the agents/skill.

### Optional companion: SwiftUI Pro

The `ios-developer` agent uses the third-party [`swiftui-pro`](https://github.com/twostraws/SwiftUI-Agent-Skill) skill (MIT licensed) to review SwiftUI code for common mistakes — see SwiftUI Pro Integration below. This is a separate plugin, not bundled with `ios-genesis`. It's optional but recommended:

```
/plugin marketplace add twostraws/SwiftUI-Agent-Skill
/plugin install swiftui-pro@swiftui-agent-skill
```

If it's not installed, `ios-developer` simply skips the SwiftUI review pass.

## Checkpoints

Each subagent reports back to the orchestrator with a short summary of what it did, plus any **risks** (e.g., "this approach assumes X, which may need revisiting") or **blockers** (e.g., "couldn't find an API key for the push notification service — feature is stubbed out") it identified during the phase. Both lists may be empty.

After each phase completes, the orchestrator:

1. Updates `.ios-orchestrator/state.json` (see State File below), including any new entries in `open_risks`.
2. Presents a brief summary of what the phase produced or changed (e.g., "Architect wrote `docs/architecture.md` — 3 modules: ..." or "Developer implemented X, build succeeded"), followed by a **Risks/Blockers** subsection listing all *currently open* items from `open_risks` (not just ones raised this phase) — so stakeholders see the cumulative picture, not just this phase's news. If `open_risks` is empty, this subsection reads "Risks/Blockers: none".
3. Asks the user via `AskUserQuestion`: **Continue to the next phase / Make changes first / Stop here**.
   - "Make changes first" lets the user give feedback, which the orchestrator relays to the same agent for a follow-up dispatch before re-presenting the checkpoint.
   - "Stop here" ends the run; state is already saved for resuming later.

An `open_risks` entry is removed in two ways: (a) the user resolves or dismisses it as part of checkpoint feedback (referencing it by `id`), or (b) a later subagent's report explicitly references the `id` and states it's been resolved by its work (e.g., the developer found the missing API key and un-stubbed the feature). Entries are never silently dropped — only removed via one of these two explicit paths.

## Subagent Roster

| Agent | Model | Responsibility | Key tools |
|---|---|---|---|
| **ios-architect** | Sonnet | Given the orchestrator's interview output (see Orchestrator Interview), turns it into requirements + architecture (modules, data flow, frameworks), writes `docs/architecture.md` (new app) or a scope summary (feature addition) — affected modules/files, etc. Reports back to the orchestrator whether the change affects screens/UI (`screens_affected: true/false`), which the orchestrator uses to decide whether to run the UI Designer phase. | Read, Grep, Glob, Write |
| **ios-ui-designer** | Sonnet | Defines screen list, navigation flow, and SwiftUI view hierarchy per screen (component breakdown, state, HIG considerations). Writes `docs/design.md`. Skipped for feature additions unless new/changed screens are needed. If `design_mode` is `figma`, also generates mockups in Figma (see Design Mode) and links the file from `docs/design.md`. If `design_mode` is `bring_your_own`, reads `design_sources` and transcribes them into `docs/design.md` instead of designing from scratch. | Read, Write (+ Figma MCP tools if `design_mode` is `figma`; + WebFetch if any `design_sources` are URLs) |
| **ios-developer** | Sonnet | Scaffolds the Xcode project (new) or modifies the existing one. Implements views/models/services per the design. Runs `xcodebuild build` / `swift build` until it compiles. If the `swiftui-pro` skill is available, invokes it to review SwiftUI code for common mistakes (see SwiftUI Pro Integration). Creates feature branches, commits, pushes, and opens PRs. Addresses reviewer feedback. | Read, Write, Edit, Bash, Skill |
| **ios-test-engineer** | Sonnet | Writes/updates unit and UI tests for new or changed functionality. Runs `xcodebuild test` until passing. Re-runs tests after reviewer-driven fixes if behavior changed. | Read, Write, Edit, Bash |
| **ios-code-reviewer** | Sonnet | Reviews the PR via `gh pr diff`/`gh pr view`, posts comments via `gh pr review`/`gh pr comment`. Approves via `gh pr review --approve` once satisfied. | Read, Grep, Glob, Bash |
| **ios-release-manager** | Haiku | New app only (or on request): versioning, Info.plist setup, app icon/asset catalog checklist, App Store readiness notes. Writes `docs/release-checklist.md`. | Read, Write, Edit |

The orchestrator (the skill, run in the user's main session) inherits the session's model.

## Role Boundaries & Scope Discipline

Tool access already constrains agents somewhat (e.g., the Architect and UI Designer have no `Edit`/`Bash`, so they can't write source code or run builds). On top of that, each agent's prompt includes an explicit "stay in your lane" instruction, and the orchestrator performs a post-hoc scope check after every phase.

| Agent | In scope | Explicitly out of scope |
|---|---|---|
| **ios-architect** | Requirements, architecture decisions, module breakdown; `docs/architecture.md` or scope summary | Does not design specific screens/layouts (defer to UI Designer) or write any Swift/test code |
| **ios-ui-designer** | Screen list, navigation, view hierarchy, component breakdown; `docs/design.md` (+ mockups per Design Mode) | Does not change architecture decisions in `docs/architecture.md`, and does not write Swift implementation code |
| **ios-developer** | Implementation code, project scaffolding, builds, branches/commits/PRs | Does not redefine architecture or screen designs; if implementation reveals that `docs/architecture.md`/`docs/design.md` need to change, raises this as an `open_risks` entry for the user rather than silently rewriting those docs |
| **ios-test-engineer** | Test code (unit/UI test targets), running tests | Does not modify app/source code — if a test failure points to an app bug, raises it as an `open_risks` entry (or, during the PR review loop, the Code Reviewer/Developer handle the fix) rather than fixing app code itself |
| **ios-code-reviewer** | PR review comments and approval | Does not push code changes itself — all fixes go back through the Developer/Test Engineer |
| **ios-release-manager** | Versioning, Info.plist, asset catalog checklist, `docs/release-checklist.md` | Does not modify app logic, views, or tests |

**Scope check**: after each phase, before presenting the checkpoint, the orchestrator checks which files changed and compares them against that phase's expected path patterns. `state.json` itself is exempt from this check in every phase (the orchestrator updates it after every phase as part of normal bookkeeping). For `bring_your_own` design sources, the files the UI Designer *reads* (per `design_sources`) are inputs, not outputs, and are never flagged regardless of where they live.

Whether the orchestrator uses `git status --porcelain` (uncommitted changes) or a diff against `last_commit_sha` (committed changes) depends on whether the phase commits its own work:

- **architect, ui_designer, test_engineer, release_manager**: these phases don't commit — use `git status --porcelain`.
- **developer, pr_creation**: the Developer commits and pushes as part of these phases, so `git status --porcelain` may be clean — use `git diff --name-only <last_commit_sha> HEAD` instead, then update `last_commit_sha` to the new HEAD.
- **code_review, merge**: no local file changes expected from either; a scope check isn't meaningful here and is skipped. (`merge`'s `gh pr merge` does change the remote default branch, but that's the intended outcome of this phase, not a violation to check for.)

| Phase | Expected paths |
|---|---|
| architect | `docs/architecture.md` |
| ui_designer | `docs/design.md` (Figma/Claude Design mockups are external, not local files) |
| developer | Source/project files (`*.swift`, `Package.swift`, `*.xcodeproj`/`*.xcworkspace`, asset catalogs) — not `docs/architecture.md` or `docs/design.md` |
| test_engineer | Test target files (`*Tests.swift` or equivalent) |
| pr_creation | Same as `developer` (branch/commit/push only — no new file changes beyond what the Developer phase already produced) |
| release_manager | `docs/release-checklist.md`, `Info.plist`, versioning/project settings, app icon assets |

Any changed file outside the expected patterns for that phase is **not reverted automatically** — it's added to `open_risks` (e.g., "Developer modified `docs/architecture.md` — review whether this was intentional") and surfaced at the checkpoint for the user to accept or ask the agent to undo.

## Orchestrator Interview

Before dispatching the Architect, the orchestrator (running in the user's main session) invokes the `superpowers:brainstorming` skill itself to interview the user about what's being built/changed:

- Explore project context, ask clarifying questions one at a time, propose 2-3 approaches with trade-offs, and present the design in sections — following the brainstorming skill as normal through the "User approves design?" step (steps 1-5 of that skill's checklist). The visual companion (step 2) is not expected to be offered in this CLI-driven context and can be left declined/skipped.
- **Adapted terminal steps**: brainstorming's remaining steps (6: write to `docs/superpowers/specs/`, 7: spec-review subagent loop, 8: user reviews the written spec, 9: invoke `writing-plans`) are replaced. Once the design is approved (end of step 5), the orchestrator does **not** write to `docs/superpowers/specs/`, run a spec-review loop, or invoke `writing-plans` — the orchestrator's own phase sequence (Architect → UI Designer → Developer → ...) is the implementation plan.
- The approved interview output (requirements, chosen approach, design summary) is passed to the Architect as input for its phase — the Architect turns it into `docs/architecture.md` (new app) or a scope summary (feature addition).

## Design Mode

`screens_affected` is determined by the Architect (phase 1), so the orchestrator can't ask about design mode during its own interview (phase 0). Instead: once the user selects "Continue to the next phase" at the Architect's checkpoint, if `screens_affected: true` and `design_mode` is not yet set, the orchestrator asks a follow-up `AskUserQuestion` (before dispatching the UI Designer) for how the user wants UI design handled. If `screens_affected: false`, this question is skipped entirely (and `design_mode` stays unset) — this applies the same way to both new apps and feature additions, even though new apps will almost always report `screens_affected: true`. If the user picks "Make changes first" or "Stop here" at the Architect checkpoint, the design-mode question is deferred until a later "Continue" is selected.

Options:

- **Text-only (default/recommended)** — the UI Designer writes `docs/design.md` only (screen list, navigation, SwiftUI view hierarchy/component breakdown). The checkpoint after this phase is the user's design review.
- **Figma** — in addition to `docs/design.md`, the UI Designer generates mockups in Figma. Before offering this option, the orchestrator checks that the Figma MCP server is available; if not, this option is omitted (text-only and Claude Design remain available). The UI Designer must follow the `/figma-use` skill before calling `use_figma`/`generate_figma_design` (per the Figma MCP server's own instructions), and links the resulting file from `docs/design.md` and the checkpoint summary.
- **Claude Design (manual)** — the UI Designer writes `docs/design.md` as in the text-only case. At this phase's checkpoint, the orchestrator additionally presents a copy-pasteable summary of the screens/flows and instructions for the user to paste it into Claude Design (claude.ai) to generate visual mockups and review/iterate there. No automation or artifact capture happens on the orchestrator's side — the standard checkpoint choices (Continue/Make changes/Stop) apply as-is, with "Continue" understood to mean the user is satisfied (whether or not they used Claude Design) and `docs/design.md` remains the spec the Developer codes against.
- **Bring your own designs** — the user already has designs from another tool (Sketch, screenshots of mockups, a Figma file they made themselves, an exported spec, etc.). The orchestrator asks the user for the relevant file paths/URLs/links, and the UI Designer reads them (images, PDFs, linked files) and translates them into `docs/design.md` (screen list, navigation, SwiftUI view hierarchy/component breakdown) referencing the original artifacts by path/URL — i.e. the UI Designer's role becomes "transcribe this existing design into our spec format" rather than "design from scratch." If the provided artifacts don't cover everything (e.g., missing screens or flows) or a source is unreadable (broken link, missing file), the UI Designer fills the gap itself and notes which parts were user-provided vs. its own additions in `docs/design.md` and the checkpoint summary. The checkpoint after this phase is the same design review as text-only, plus these provenance notes.

The choice is recorded as `design_mode: "text" | "figma" | "claude_design" | "bring_your_own"` in `state.json`. If the user doesn't express a preference, the orchestrator defaults to `"text"`. For `"bring_your_own"`, the provided file paths/URLs are recorded in `state.json` as `design_sources` (a list of strings) and passed to the UI Designer.

## SwiftUI Pro Integration

Before implementing, the `ios-developer` agent checks whether the `swiftui-pro` skill is available by invoking the `Skill` tool with `swiftui-pro`; if the tool reports no such skill exists, the Developer proceeds without it. If it is available:

- After the implementation builds successfully (`xcodebuild build`/`swift build` passes), the Developer invokes `/swiftui-pro` to review the SwiftUI views/code it just wrote for common mistakes (deprecated APIs, accessibility/VoiceOver issues, performance problems, navigation/layout/state-management anti-patterns).
- If `/swiftui-pro` suggests changes, the Developer applies fixes for clear correctness, deprecation, and accessibility issues, and uses its judgment on purely stylistic suggestions, then rebuilds to confirm the project still compiles.
- This happens once per Developer dispatch (initial implementation and each `address_review` round), after the build succeeds and before committing.
- Any resulting edits are part of the Developer phase's normal output (same `*.swift` files already in scope) — no separate scope-check category or `open_risks` entry is needed for them.
- The Developer's checkpoint summary notes whether this pass ran and, if so, what it changed (e.g., "SwiftUI Pro review: applied 2 accessibility fixes") or that it was skipped because `swiftui-pro` isn't installed.

If `swiftui-pro` is not installed, this step is skipped silently — it's an optional quality pass, not a hard dependency, and its absence is not raised as an `open_risks` entry. If it *is* installed but the invocation itself errors, the Developer treats that as part of its existing build-fix-rebuild retry budget (see Error Handling & Edge Cases) rather than a separate failure mode — if it can't get a useful result after retrying, it proceeds without the review and notes this in its checkpoint summary.

## Orchestration Flow

### New app
(target path doesn't exist, or exists but has no `.ios-orchestrator/state.json`)

0. **Orchestrator interview** — orchestrator interviews the user via `superpowers:brainstorming` (see Orchestrator Interview)
1. **Architect** — turns the interview output into requirements + architecture, writes `docs/architecture.md` → checkpoint
2. **UI Designer** — screens, navigation, view hierarchy → `docs/design.md` → checkpoint
3. **Developer** — scaffolds Xcode project, implements per design, runs `xcodebuild build`/`swift build` until it compiles → checkpoint
4. **Test Engineer** — writes unit/UI tests, runs `xcodebuild test` until passing → checkpoint
5. **PR creation** — Developer commits to a feature branch named `feature/initial-implementation`, pushes, and opens a PR describing the build, referencing `docs/architecture.md`/`docs/design.md`.
   - If no GitHub remote exists: orchestrator checkpoints with the user — create a GitHub repo (public/private)? If yes, `gh repo create`, then push and open PR.
6. **Code Reviewer** — reviews the PR; loops with Developer (and Test Engineer if behavior changes) until approved or max rounds reached (max 2, see PR-Based Review Flow) → checkpoint
7. **Auto-merge** — once approved, orchestrator runs `gh pr merge` (squash); if it fails (conflicts, pending/failed required checks), surface the `gh` error to the user rather than retrying
8. **Release Manager** — versioning, Info.plist, icon/asset checklist → `docs/release-checklist.md` → checkpoint

### Feature addition
(state file exists, or project exists but has no state file — orchestrator initializes one and has the Architect do a quick codebase survey first)

0. **Orchestrator interview** — orchestrator interviews the user via `superpowers:brainstorming` (see Orchestrator Interview)
1. **Architect** — turns the interview output into a scoped change, identifies affected modules/files → checkpoint
2. **UI Designer** — only if the architect reported `screens_affected: true`; otherwise skipped
3. **Developer** — implements, builds → checkpoint
4. **Test Engineer** — updates/adds tests, runs → checkpoint
5. **PR creation** — Developer creates a feature branch off the project's default branch, named `feature/<slug>` where `<slug>` is derived from the change description (e.g. "add login screen" → `feature/add-login-screen`), commits, pushes, opens a PR
6. **Code Reviewer** — reviews the PR; loops with Developer (and Test Engineer) until approved or max rounds reached (max 2, see PR-Based Review Flow) → checkpoint
7. **Auto-merge** — once approved, orchestrator runs `gh pr merge` (squash); if it fails (conflicts, pending/failed required checks), surface the `gh` error to the user rather than retrying
8. **Release Manager** — skipped unless the user explicitly requests a release-readiness pass

## PR-Based Review Flow

- Requires the `gh` CLI to be authenticated. The orchestrator checks this upfront and surfaces a clear message if not.
- The Code Reviewer reviews via `gh pr diff`/`gh pr view` and posts comments via `gh pr review`/`gh pr comment`.
- If issues are found, the orchestrator re-dispatches the Developer (and Test Engineer if needed) as fresh subagents — each dispatch includes the reviewer's PR comments verbatim plus a short summary of the work done so far (from `state.json`), since subagents don't retain memory between dispatches. The Developer addresses the comments, commits, and pushes (updating the PR in place).
- The loop (Reviewer → Developer → [Test Engineer] → Reviewer) continues for up to **2 rounds**, tracked via `review_round` in `state.json`. If issues remain unresolved after round 2, the orchestrator surfaces them to the user instead of looping further.
- Once the Reviewer approves, the orchestrator runs `gh pr merge` automatically (squash merge).

## State File

`<project>/.ios-orchestrator/state.json`, written and updated by the orchestrator (not the subagents) after each phase completes.

```json
{
  "mode": "new_app",
  "phase": "code_review",
  "phase_status": "in_progress",
  "review_round": 1,
  "screens_affected": true,
  "design_mode": "text",
  "design_sources": [],
  "last_commit_sha": "a1b2c3d4...",
  "pr_url": "https://github.com/user/repo/pull/1",
  "open_risks": [
    {
      "id": "risk-1",
      "phase": "developer",
      "raised_at": "2026-06-11T10:45:00Z",
      "description": "No push notification API key found — feature stubbed out pending credentials."
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
      "completed_at": "2026-06-11T10:20:00Z",
      "summary": "2 screens: ItemList, ItemDetail.",
      "artifact": "docs/design.md"
    }
  ]
}
```

- `mode`: `"new_app"` or `"feature_addition"`.
- `phase`: one of `architect`, `ui_designer`, `developer`, `test_engineer`, `pr_creation`, `code_review`, `merge`, `release_manager`.
- `phase_status`: `"in_progress"` or `"complete"`.
- `review_round`: current round of the PR review loop (see PR-Based Review Flow), reset to 0 before the first review.
- `last_commit_sha`: HEAD of the project's default branch as of the last orchestrator update — used for drift detection.
- `design_mode`: `"text"`, `"figma"`, `"claude_design"`, or `"bring_your_own"` — see Design Mode. Only meaningful when `screens_affected` is `true`; otherwise unset.
- `design_sources`: list of file paths/URLs to user-provided designs, only populated when `design_mode` is `"bring_your_own"`; empty otherwise.
- `open_risks`: list of risks/blockers raised by subagents that haven't been resolved or dismissed yet. Each entry has a stable `id` (e.g. `risk-1`, `risk-2`, incrementing), the `phase` that raised it (using the same short names as the `phase` field above), `raised_at`, and a `description`. Surfaced at every checkpoint until removed by `id` — either the user dismisses/resolves it at a checkpoint, or a later subagent's report references the `id` as resolved by its work.

On resume, the orchestrator reads this file to determine where to pick up. Before continuing, it runs `git rev-parse HEAD` on the project's default branch and compares it to `last_commit_sha`:

- **Match**: proceed from `phase`/`phase_status` as recorded.
- **Mismatch**: flag the drift to the user (see Error Handling) and ask whether to proceed, re-run the current phase, or have the Architect re-scope first.

## Error Handling & Edge Cases

- **Build/test failures**: Developer/Test Engineer retry fixes themselves (build → fix → rebuild) up to ~3 attempts before surfacing the failure to the user with the error output. The same retry budget covers a `/swiftui-pro` review invocation that errors (see SwiftUI Pro Integration).
- **Code review loop**: capped at 2 rounds (see PR-Based Review Flow above); unresolved issues after that are surfaced to the user.
- **Ambiguous requirements**: handled by the orchestrator's `superpowers:brainstorming` interview (see Orchestrator Interview), which asks clarifying questions before any design is written.
- **Resuming with drift**: if `.ios-orchestrator/state.json` exists but `git rev-parse HEAD` no longer matches `last_commit_sha`, the orchestrator flags this and asks whether to proceed, re-run the affected phase, or have the Architect re-scope first.
- **Existing non-orchestrator project**: if the target path has an Xcode project but no state file, treat it as "feature addition, first run" — initialize a state file and have the Architect do a quick codebase survey before scoping the change.
- **No GitHub remote (new app)**: orchestrator checkpoints with the user before creating a repo via `gh repo create`.
- **`gh` CLI not authenticated**: orchestrator surfaces this to the user before reaching the PR creation step.

## Validation

No traditional unit test suite applies, since this project produces agent/skill *definitions* (markdown + prompts). Validation is a real end-to-end dry run: after writing the agents and skill, run `/ios-genesis` against a small throwaway app spec (e.g., a simple single-screen counter app) in a scratch directory, and confirm each phase runs, produces the expected docs, the PR review loop functions, and the final app builds and passes tests.

To exercise the GitHub flow without creating throwaway public repos, use a pre-existing private scratch repo (created once, reused across dry runs) rather than letting `gh repo create` run fresh each time.
