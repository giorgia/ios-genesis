# ios-genesis v0.4.0 — Architecture Artifact Format

## Problem

The architect checkpoint hands the user `docs/architecture.md` as prose and bullet lists. Reviewing it is tedious: there are no visuals, no data-model schema, and no way to consume the plan in a richer surface (a rendered doc, a shared Google Doc) even when the tooling to do so is connected. The user wants schema and diagrams at this checkpoint, and — for users whose sessions have the relevant MCP connected — the option to publish the plan into an external tool, without the pipeline hard-wiring any single destination.

## Decisions made during brainstorming

- **User chooses the format**, at runtime, at the architect checkpoint — a new selection parallel to `design_mode`, not a hard-coded destination.
- **Always ask**, even when markdown is the only available option. Never silently default.
- **The menu is gated by connected MCPs**, mirroring how `design-mode.md` omits the Figma option when the Figma MCP is absent. Markdown is always offered; Google Docs appears only if the Drive MCP is connected; Jira/Notion/Confluence only if theirs are.
- **Enriched markdown is always the source of truth (Approach A).** External formats are rendered *from* it, never instead of it — so there is never a plain-vs-rich split by machine, and later phases always have the rich `.md`.
- **The architect writes the markdown; the orchestrator publishes externally.** The architect subagent has no MCP access (`tools: Read, Grep, Glob, Write`); the orchestrator main session does. So the architect always produces the enriched `.md`, and the orchestrator performs any external publish during the checkpoint.
- **v1 concrete targets: enriched markdown (always) + Google Docs.** Jira/Notion/Confluence are designed as extension points (offered when their MCP is present) but their publishers are deferred.

## 1. Enriched `architecture.md` (always produced)

`agents/ios-architect.md`'s output template gains visuals and a schema, all in mermaid so they render in GitHub / VS Code preview / Obsidian with zero dependencies:

- `## Modules` — add a `graph TD` module-dependency diagram alongside the existing responsibility list.
- `## Data Flow` — add a flowchart (or `sequenceDiagram`) alongside the prose.
- `## Schema` — **new section.** The data model as an `erDiagram` (or `classDiagram` for model classes) plus a table of entities, fields, and types. The architect emits no schema today; this is new content and the "schema" half of the request.

Unchanged: `## Overview`, `## Screens`, `## Risks`.

`feature_addition` mode writes no file (the architect returns a scope summary — see `agents/ios-architect.md`). The enriched content (including mermaid) goes into that returned summary text and the persisted `architecture_summary`; there is no `.md` file and no external publish is offered in this mode unless a summary file is later introduced. (See Deferred.)

## 2. The format question (`references/architecture-format.md`, new)

A new reference document, parallel to `design-mode.md`, referenced from `SKILL.md` and invoked at the post-architect checkpoint (before advancing to the next phase).

- **Detect available targets:** scan the session tool list for the relevant MCP prefixes — `mcp__*Google_Drive*` (Google Docs), `mcp__*Atlassian*` (Jira/Confluence), etc. — the same availability check `design-mode.md` uses for Figma.
- **Always ask** via `AskUserQuestion`. Options: **Markdown** (always, recommended default) + one entry per connected external target. When markdown is the only option, still present the question as a single-choice confirmation rather than skipping it (satisfies "ask anyway").
- **Persist** the choice as `architecture_format` in `state.json`; persist any resulting external artifact URL as `architecture_artifact_url`.

## 3. External publish — Google Docs (orchestrator, at the checkpoint)

When the user selects Google Docs:

1. Orchestrator renders the enriched `architecture.md` to a single self-contained HTML string — schema/tables as HTML `<table>`, mermaid diagrams rendered to inline images (see dependency below).
2. Upload via the Drive MCP `create_file` with `content_mime_type: "text/html"` (Drive converts `text/html` → a native Google Doc, preserving tables and inline images — validated against the live MCP schema during brainstorming).
3. Surface the returned Doc link at the checkpoint and store it as `architecture_artifact_url` in `state.json`.

**Dependency:** the HTML/Google-Docs path needs a mermaid-to-image renderer (e.g. `mmdc` from `@mermaid-js/mermaid-cli`). If it is not installed, **degrade gracefully** — publish the Doc with the diagram source shown as preformatted code plus a note that image rendering was skipped, and raise an `open_risks` entry; never fail the run over a missing renderer. The markdown path needs no renderer (viewers render mermaid natively).

## 4. Checkpoint presentation

`references/checkpoints.md` step 5 (present the summary) additionally states the chosen `architecture_format` and, when an external artifact was produced, includes the `architecture_artifact_url`. The existing content-surfacing of `architecture.md` is unchanged.

## 5. State schema

`references/state-schema.md` gains two fields:

- `architecture_format`: `"markdown"` | `"google_docs"` | (future: `"jira"`, `"notion"`, `"confluence"`). Set at the architect checkpoint. Defaults to `"markdown"`.
- `architecture_artifact_url`: URL of the published external artifact when one was created; unset (key omitted) otherwise.

Both set during the architect checkpoint; carried through resume.

## 6. Affected documents

- `agents/ios-architect.md` — enriched output template (Modules/Data Flow diagrams + new Schema section).
- `skills/ios-genesis/references/architecture-format.md` — **new**; the ask + MCP detection + per-format publish.
- `skills/ios-genesis/SKILL.md` — reference the new doc under "Reference docs".
- `skills/ios-genesis/references/orchestration-flow.md` — the post-architect checkpoint invokes the format question.
- `skills/ios-genesis/references/checkpoints.md` — present `architecture_format` + artifact URL.
- `skills/ios-genesis/references/state-schema.md` — `architecture_format` + `architecture_artifact_url` fields + initialization.
- `.claude-plugin/plugin.json` — version bump to `0.4.0`.
- `README.md` — document the architecture-format choice.

## 7. Deferred (explicitly out of scope for v1)

- **Jira / Notion / Confluence publishers.** The menu offers them when their MCP is connected, but wiring each publisher is later work. v1 ships the extensible pattern + the Google Docs publisher only.
- **PDF output.** Derivable from the HTML render via an HTML→PDF step; a fast-follow, not v1.
- **External publish for `feature_addition`.** No `.md` artifact exists in that mode; revisit if a persisted architecture summary file is introduced.
- **Re-publish / sync on "Make changes first".** v1 publishes once when the format is chosen; keeping an external Doc in sync across architect re-dispatches is future work.

## Validation plan

- New-app run, no external MCP connected: confirm the format question is still asked (markdown-only, single option) and `architecture.md` contains the module diagram, data-flow diagram, and schema section, all rendering in a mermaid-aware viewer.
- New-app run with Drive MCP connected: confirm Google Docs appears in the menu; selecting it produces a Doc with tables + diagram images and surfaces the link at the checkpoint; verify `architecture_format`/`architecture_artifact_url` persist and survive resume.
- Missing `mmdc`: confirm graceful degradation (Doc published with diagram source as code + risk raised), run not failed.
- Scope check: the new architect content stays within `docs/architecture.md`; no boundary regressions.
