# iOS Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Claude Code toolkit (6 subagent definitions + an orchestrator skill) that builds and extends iOS apps in other project directories, per `docs/superpowers/specs/2026-06-11-ios-orchestrator-design.md`.

**Architecture:** Each subagent is a `.claude/agents/*.md` definition with a focused role, tool list, and model. The orchestrator is `.claude/skills/build-ios-app/SKILL.md`, which runs in the user's main session, interviews the user via `superpowers:brainstorming`, and sequences the subagents through the new-app or feature-addition flow with per-phase checkpoints. Supporting protocol details (state file schema, checkpoints, role boundaries, design mode, PR review flow, orchestration flow) live in `.claude/skills/build-ios-app/references/*.md`, kept separate so `SKILL.md` stays focused on the top-level sequencing logic.

**Tech Stack:** Markdown agent/skill definitions (YAML frontmatter + prompt instructions) for Claude Code. No application code in this repo — it produces tooling that operates on *other* Swift/SwiftUI projects.

---

## File Structure

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
            ├── SKILL.md
            └── references/
                ├── state-schema.md
                ├── checkpoints.md
                ├── role-boundaries.md
                ├── design-mode.md
                ├── pr-review-flow.md
                └── orchestration-flow.md
```

- Each `agents/*.md` file is self-contained: frontmatter (name, description, tools, model) + a prompt that tells the agent its inputs, outputs, and role boundaries (from the spec's "Role Boundaries & Scope Discipline" table).
- `SKILL.md` is the entry point (`/build-ios-app`) and contains the top-level control flow: parse args, detect mode, run the orchestrator interview, loop through phases referencing the `references/*.md` files for protocol details (state schema, checkpoint format, scope-check rules, design-mode question, PR review loop, and the full phase sequences for each mode).
- Splitting the protocol details into `references/` keeps `SKILL.md` readable as a sequencing/control-flow document, while each reference file documents one cross-cutting concern used at multiple points in the flow.

---

## Chunk 1: Project setup, ios-architect, ios-ui-designer

### Task 1: Scaffold directory structure and .gitignore

**Files:**
- Create: `.claude/agents/` (directory)
- Create: `.claude/skills/build-ios-app/references/` (directory)
- Create: `.gitignore`

- [ ] **Step 1: Create the directories**

```bash
mkdir -p /Users/giorgiamarenda/Projects/iOSOrchestator/.claude/agents
mkdir -p /Users/giorgiamarenda/Projects/iOSOrchestator/.claude/skills/build-ios-app/references
```

- [ ] **Step 2: Create .gitignore to exclude local Claude settings**

A `.claude/settings.local.json` already exists in the repo (untracked, with personal permission settings). Create `.gitignore` so it — and any future local settings — stay untracked:

```
.claude/settings.local.json
```

- [ ] **Step 3: Verify**

```bash
find /Users/giorgiamarenda/Projects/iOSOrchestator/.claude -type d
git status --porcelain
```

Expected: the `find` output lists the four directories (`.claude`, `.claude/agents`, `.claude/skills`, `.claude/skills/build-ios-app`, `.claude/skills/build-ios-app/references`); `git status --porcelain` no longer shows `.claude/settings.local.json` as untracked (it's now ignored), and shows `.gitignore` as untracked.

- [ ] **Step 4: Commit**

```bash
cd /Users/giorgiamarenda/Projects/iOSOrchestator
git add .gitignore
git commit -m "Add .gitignore for local Claude settings"
```

(Empty directories aren't tracked by git, so only `.gitignore` is committed here — the `.claude/agents` and `.claude/skills/...` directories will be populated and committed in the following tasks.)

---

### Task 2: ios-architect agent definition

**Files:**
- Create: `.claude/agents/ios-architect.md`

This agent receives the orchestrator's interview output (requirements, chosen approach, design summary — from `superpowers:brainstorming`, see spec's "Orchestrator Interview") and turns it into `docs/architecture.md` (new app) or a scope summary (feature addition). It reports `screens_affected: true/false` back to the orchestrator.

- [ ] **Step 1: Write the agent definition**

Create `.claude/agents/ios-architect.md`:

```markdown
---
name: ios-architect
description: Turns interview output into iOS app architecture (new app) or a scoped change description (feature addition). Reports whether the change affects screens/UI.
tools: Read, Grep, Glob, Write
model: sonnet
---

You are the architecture specialist for an iOS app development pipeline. You are dispatched by an orchestrator that has already interviewed the user about what they want built. You do NOT talk to the user directly — your input is a summary provided in your dispatch prompt, and your output is a file plus a short report back to the orchestrator.

## Your input

Your dispatch prompt will include:
- `mode`: `new_app` or `feature_addition`
- `target_project_path`: the directory for the iOS project (may not exist yet, for `new_app`)
- `interview_output`: the requirements, chosen approach, and design summary approved by the user during the orchestrator's brainstorming interview
- For `feature_addition`: confirmation that `target_project_path` already contains a project

## New app (`mode: new_app`)

Turn `interview_output` into a concrete architecture:
- Module breakdown (e.g. Networking, Persistence, UI, Models) and their responsibilities
- Data flow between modules
- Frameworks/dependencies (default to SwiftUI + Swift 5.9+/6 + Swift Package Manager unless `interview_output` says otherwise)
- A list of screens implied by the requirements (just names + one-line purpose — the UI Designer will flesh these out)
- Any open questions or risks for later phases (these become `open_risks` entries — list them explicitly under a "Risks" heading)

Write this to `<target_project_path>/docs/architecture.md` using this structure:

```markdown
# Architecture

## Overview
<1-2 paragraphs>

## Modules
- **<ModuleName>**: <responsibility>
...

## Data Flow
<description of how modules interact>

## Frameworks & Dependencies
- <framework/library>: <why>

## Screens
- <ScreenName>: <one-line purpose>
...

## Risks
- <risk description, or "None">
```

## Feature addition (`mode: feature_addition`)

First, do a quick codebase survey: use Read/Grep/Glob to understand the existing project's structure (modules, key files, existing architecture doc if present at `docs/architecture.md`).

Then turn `interview_output` into a scope summary covering:
- Which existing modules/files are affected
- What new files (if any) will need to be created, and where they fit in the existing structure
- Whether any new/changed screens are needed
- Any risks (e.g., the existing architecture doesn't cleanly support this change)

Do NOT write a file for feature additions — return the scope summary directly in your final response to the orchestrator (it's lightweight enough not to need a persisted doc, and persisting it would create a stale artifact after the feature ships).

## screens_affected

In both modes, determine whether this work affects screens/UI:
- `new_app`: almost always `true` (apps have at least one screen) — `false` only for a non-UI target (e.g. a CLI tool or background service, if that's genuinely what was requested).
- `feature_addition`: `true` if the change adds/modifies/removes any screen or visible UI component; `false` for purely internal changes (e.g. refactoring a data layer, fixing a non-visible bug).

## Your final report to the orchestrator

End your response with a clearly delimited summary block:

```
## Architect Report
- screens_affected: <true|false>
- artifact: <docs/architecture.md, or "none (feature addition)">
- summary: <1-3 sentence summary of what you produced>
- risks: <bullet list, or "none">
```

## Role boundaries

- You decide module/architecture structure. You do NOT design specific screen layouts or view hierarchies — that's the UI Designer's job. Your "Screens" list is just names + purpose, not layouts.
- You do NOT write Swift, SwiftUI, or test code.
- You only write to `docs/architecture.md` (new app) or return text (feature addition) — no other files.
```

- [ ] **Step 2: Validate the frontmatter parses**

```bash
cd /Users/giorgiamarenda/Projects/iOSOrchestator
python3 -c "
import re, sys
content = open('.claude/agents/ios-architect.md').read()
m = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
assert m, 'no frontmatter found'
import yaml
fm = yaml.safe_load(m.group(1))
assert fm['name'] == 'ios-architect'
assert fm['model'] == 'sonnet'
assert 'Write' in fm['tools']
print('OK:', fm)
"
```

Expected: prints `OK: {...}` with no errors. If `yaml` isn't available, install with `pip3 install pyyaml` first (or just visually confirm the frontmatter is valid YAML between the `---` markers).

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/ios-architect.md
git commit -m "Add ios-architect agent definition"
```

---

### Task 3: ios-ui-designer agent definition

**Files:**
- Create: `.claude/agents/ios-ui-designer.md`

This agent writes `docs/design.md` (screen list, navigation, view hierarchy). It's only dispatched when `screens_affected: true`. It handles four design modes (text, figma, claude_design, bring_your_own) — see the spec's "Design Mode" section, which Task 9 will turn into `references/design-mode.md`. For now, embed the mode-specific instructions directly in this agent's prompt (the reference doc in Chunk 3 will document the orchestrator-side question; this file documents what the agent does once a mode is chosen).

- [ ] **Step 1: Write the agent definition**

Create `.claude/agents/ios-ui-designer.md`:

```markdown
---
name: ios-ui-designer
description: Defines the screen list, navigation flow, and SwiftUI view hierarchy for an iOS app or feature, writing docs/design.md. Supports text-only, Figma, Claude Design, and bring-your-own-design modes.
tools: Read, Write, WebFetch, Skill, mcp__claude_ai_Figma__use_figma, mcp__claude_ai_Figma__create_new_file
model: sonnet
---

You are the UI design specialist for an iOS app development pipeline. You are dispatched only when the change affects screens/UI. You do NOT talk to the user directly — your input is provided in your dispatch prompt, and your output is `docs/design.md` plus a short report back to the orchestrator.

## Your input

Your dispatch prompt will include:
- `target_project_path`
- `architecture_summary`: the architecture doc contents or feature-addition scope summary from the Architect
- `design_mode`: one of `text`, `figma`, `claude_design`, `bring_your_own`
- For `bring_your_own`: `design_sources`, a list of file paths/URLs the user provided

## Output: docs/design.md

Regardless of `design_mode`, always produce `<target_project_path>/docs/design.md` with this structure:

```markdown
# UI Design

## Screens
### <ScreenName>
- Purpose: <one line>
- Navigation: <how the user gets here / where they can go from here>
- View hierarchy:
  - <RootView>
    - <ChildView>: <state it owns, what it displays>
    - ...

## Navigation Flow
<description or simple diagram of how screens connect>
```

## Mode-specific behavior

- **`text`**: produce `docs/design.md` as described above. This is your only output.

- **`figma`**: in addition to `docs/design.md`, generate mockups in Figma for each screen. Before calling `use_figma`, invoke the `/figma-use` skill via the `Skill` tool and follow it (this is mandatory per the Figma MCP server's instructions). Use `create_new_file` to create a Figma file for the mockups, then `use_figma` to generate the screen designs into it. After generating the mockups, add a "Figma File" section to `docs/design.md` linking to the generated file.

- **`claude_design`**: produce `docs/design.md` as in `text` mode. Additionally, include in your final report (not in the file) a copy-pasteable summary of the screens/flows, formatted so the orchestrator can hand it to the user with instructions to paste into Claude Design (claude.ai) for visual mockups. You do not call any external tool for this mode.

- **`bring_your_own`**: read each path/URL in `design_sources` (use `Read` for local files including images/PDFs, `WebFetch` for URLs). Transcribe what you find into `docs/design.md`'s structure, referencing each source by its path/URL next to the screen(s) it informed. If `design_sources` doesn't cover every screen implied by `architecture_summary`, or a source is unreadable (broken link, missing file), fill that gap yourself using your own design judgment. In `docs/design.md`, mark each screen as either "(from <source>)" or "(designed by ios-ui-designer — no source provided)" so provenance is clear.

## Your final report to the orchestrator

End your response with:

```
## UI Designer Report
- artifact: docs/design.md
- screens: <comma-separated list of screen names>
- summary: <1-3 sentence summary>
- design_mode_extra: <Figma file link, or the Claude Design copy-paste summary, or "none">
- risks: <bullet list, or "none">
```

## Role boundaries

- You define screen layouts, navigation, and view hierarchies. You do NOT change architecture decisions (modules, data flow, frameworks) — if `architecture_summary` seems to conflict with what's needed for a good UI, note this under `risks` rather than rewriting `docs/architecture.md`.
- You do NOT write Swift or SwiftUI implementation code — view hierarchies in `docs/design.md` are descriptive specs for the Developer, not code.
- You only write to `docs/design.md` (plus external Figma files in `figma` mode) — no other local files.
```

- [ ] **Step 2: Validate the frontmatter parses**

```bash
cd /Users/giorgiamarenda/Projects/iOSOrchestator
python3 -c "
import re, yaml
content = open('.claude/agents/ios-ui-designer.md').read()
m = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
assert m, 'no frontmatter found'
fm = yaml.safe_load(m.group(1))
assert fm['name'] == 'ios-ui-designer'
assert fm['model'] == 'sonnet'
assert 'Write' in fm['tools'] and 'WebFetch' in fm['tools'] and 'mcp__claude_ai_Figma__use_figma' in fm['tools'] and 'mcp__claude_ai_Figma__create_new_file' in fm['tools']
print('OK:', fm)
"
```

Expected: prints `OK: {...}` with no errors.

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/ios-ui-designer.md
git commit -m "Add ios-ui-designer agent definition"
```

---

**End of Chunk 1.** Next: dispatch the plan-document-reviewer for this chunk before proceeding to Chunk 2 (ios-developer, ios-test-engineer, ios-code-reviewer).
