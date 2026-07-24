# Issue-Driven Runs Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `/ios-genesis` `feature_addition` runs consume selected GitHub Issues as their requirements input and auto-close them when the run's PR merges.

**Architecture:** Orchestrator-driven and documentation-only — no Swift, no new agents. At Step 0 the orchestrator (which already drives `gh`) detects a GitHub remote, offers/accepts an issue selection, and persists it as `source_issues` in `state.json` at initialization. The selected issues seed the existing Step 0 interview. Before the `create_pr` dispatch, a pre-dispatch prompt lets the user drop any incomplete issue; the retained `Closes #N` list is passed through `pr_description_context` and written verbatim into the PR body, so GitHub's native auto-close fires on the existing squash-merge. The `merge` phase is unchanged.

**Tech Stack:** Markdown reference docs for the ios-genesis Claude Code plugin (`skills/ios-genesis/`), one agent-file edit (`agents/ios-developer.md`), the JSON `state.json` schema doc, `.claude-plugin/plugin.json`, and `README.md`. The plugin's "source" is prose the orchestrator follows; there are no unit tests. Each task is a focused doc edit verified by a `grep` assertion (the added text is present and internally coherent); the feature is validated end-to-end by a manual `feature_addition` run (final task).

**Spec:** `docs/superpowers/specs/2026-07-24-issue-driven-runs-design.md` (approved, review round 2).

**Working branch:** `feature/issue-driven-runs` (already created off `main`; the spec is already committed here).

**Verification note:** because this is prose, "the test" for each task is (a) a `grep` that the intended anchor text exists, and (b) a human/agent read-through that the edit is coherent with the surrounding doc. Run `grep` from the repo root `/Users/giorgiamarenda/Projects/iOSOrchestator`.

---

## Chunk 1: Input side — new reference doc, state schema, Step 0 selection

### Task 1: Create `references/issue-driven-runs.md`

**Files:**
- Create: `skills/ios-genesis/references/issue-driven-runs.md`

- [ ] **Step 1: Write the new reference doc**

Create `skills/ios-genesis/references/issue-driven-runs.md` with this content:

```markdown
# Issue-Driven Runs

Lets a `feature_addition` run take its requirements from selected GitHub Issues and close them when its PR merges. Reading and closing only — issue creation, triage, and backlog-runner autonomy are out of scope. `new_app` is not supported (there are no issues to consume yet).

## Gating (Step 0)

Only offered for `mode: feature_addition`. Before offering, confirm both:
- `gh` is available and authenticated (`gh auth status` succeeds), and
- the repo has a GitHub remote (`gh repo view` succeeds).

If either fails — or there are no open issues — do not offer the issue path; proceed with the normal free-text description interview. This is silent and never an error, mirroring how `design-mode.md` omits Figma when its MCP is absent.

## Selecting issues

**Invocation shortcut (strict grammar, no prose scanning).** Treat the `description` argument as an issue shortcut *only* when it begins with exactly one of:
- `issues:` followed by comma-separated numbers, e.g. `issues:12,13,14`
- `label:<name>`
- `milestone:<name>`

Exactly one token is honored; tokens do not combine (`label:bug milestone:v1` is unsupported in this version). Anything else — including free text that merely contains a `#`, e.g. "fix the #1 priority crash" — is a normal description, and the picker runs.

**Interactive picker (default).** When no shortcut token is present, run `gh issue list --state open --json number,title,labels`. If it returns issues, ask via `AskUserQuestion` (multi-select) "Work from existing issues, or describe fresh?" — options are the open issues plus a "No — describe fresh" escape (drops to the normal description flow). No open issues → skip silently to the normal flow.

## Fetching

For each selected issue, run `gh issue view <n> --json number,title,body,labels,url,comments`. Comments are always fetched and made available to the interview (no length heuristic).

## Seeding the interview

The fetched `title` + `body` + `labels` (+ comments) become the starting material for the Step 0 interview in place of the `description` argument. The interview runs as normal (it can ask the user to clarify terse issues) and produces `interview_output`, which notes the issue numbers it covers. Everything downstream is unchanged — the Architect scopes a task graph from `interview_output`; there is no issue→task mapping. When issues seeded the run, the Step 0 interview presentation lists the selected issue numbers and titles, and notes any that were named-but-skipped (nonexistent/already-closed).

## Persisting

Record the selection as `source_issues` (a list of `{number, title, url}`) written at **state initialization**, alongside `interview_output` (see `state-schema.md`). Between the picker and the init write it is held in-session, exactly like `interview_output`.

## Error handling (soft-fail)

Every failure degrades to the normal flow or skips the offending issue — a run is never aborted over issue handling:
- No `gh` / not authenticated / no GitHub remote / no open issues → the issue path is not offered; run the normal description interview.
- `gh issue view <n>` fails on a selected issue → surface the error and offer to retry or skip that issue; never abort the run.
- A named issue number that does not exist or is already closed → warn, skip it, and note it in the Step 0 summary.
- Empty or unset `source_issues` at pr_creation → no `Closes` lines are added; the run behaves exactly as a normal description run.

## Closing (pr_creation)

See `pr-review-flow.md`. In short: before the `create_pr` dispatch, present the `Closes #N` list (default: all of `source_issues`) via `AskUserQuestion` and let the user drop any unfinished issue; pass the retained list into `pr_description_context` so the developer writes `Closes #N` lines into the PR **body** (verbatim — required for squash-merge auto-close). The `merge` phase is unchanged; GitHub auto-closes on merge. Dropped issues stay open with no comment.
```

- [ ] **Step 2: Verify the doc exists and has the required sections**

Run: `grep -c "^## " skills/ios-genesis/references/issue-driven-runs.md`
Expected: `7` (Gating, Selecting issues, Fetching, Seeding the interview, Persisting, Error handling, Closing).

Run: `grep -n "issues:\|label:\|milestone:\|source_issues\|Closes #N\|gh issue list\|gh issue view\|warn, skip\|retry or skip" skills/ios-genesis/references/issue-driven-runs.md`
Expected: matches present (grammar tokens, state field, closing keyword, both `gh` commands, and the soft-fail warn/skip + retry rules).

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/issue-driven-runs.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "Add issue-driven-runs reference doc"
```

### Task 2: Add `source_issues` to `state-schema.md`

**Files:**
- Modify: `skills/ios-genesis/references/state-schema.md` (schema example ~line 17, Field reference after the `design_sources` bullet ~line 94, Initialization enumeration ~line 123)

- [ ] **Step 1: Add `source_issues` to the example JSON**

In the ```` ```json ```` schema block, immediately after the `"design_sources": [],` line, add:
```json
  "source_issues": [{ "number": 12, "title": "Best streak captures last, not the max", "url": "https://github.com/owner/repo/issues/12" }],
```

- [ ] **Step 2: Add a Field-reference bullet**

Immediately after the `design_sources:` field bullet, add:
```markdown
- `source_issues`: list of `{ "number": int, "title": string, "url": string }` for the GitHub Issues a `feature_addition` run was built from (see `issue-driven-runs.md`). Present only for issue-driven runs; **unset (key omitted)** otherwise. Written at initialization from the Step 0 selection; read before the `create_pr` dispatch to build the `Closes #N` list. Carried through resume unchanged.
```

- [ ] **Step 3: Add `source_issues` to the Initialization enumeration**

In the Initialization section (the sentence listing which keys are written for a brand-new run — the one ending "…`open_risks: []`, `phases_completed: []`."), insert into the enumeration, right after the `design_sources` clause:
```markdown
, `source_issues` set to the issues selected in the Step 0 interview if this is an issue-driven `feature_addition` run (otherwise unset)
```

- [ ] **Step 4: Verify**

Run: `grep -c "source_issues" skills/ios-genesis/references/state-schema.md`
Expected: `3` (example JSON, field reference, initialization enumeration).

Run: `grep -n "source_issues" skills/ios-genesis/references/state-schema.md`
Expected: one hit inside the ```` ```json ```` block, one in Field reference, one in the Initialization paragraph.

- [ ] **Step 5: Commit**

```bash
git add skills/ios-genesis/references/state-schema.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "state-schema: add source_issues field + initialization"
```

### Task 3: Add issue detection/selection to Step 0 in `orchestration-flow.md`

**Files:**
- Modify: `skills/ios-genesis/references/orchestration-flow.md` (Step 0 section, after the "Detect existing designs" bullet ~line 12; and the `interview_output` persistence bullet ~line 13)

- [ ] **Step 1: Add the issue-selection bullet to Step 0**

In `## Step 0 (both modes): Orchestrator interview`, immediately after the "**Detect existing designs**" bullet, add:
```markdown
- **Detect GitHub Issues (`feature_addition` only)**: for a `feature_addition` run, if `gh` is authenticated and the repo has a GitHub remote, offer to build the run from existing open Issues instead of (or seeding) the free-text description — see `issue-driven-runs.md` for the gating, the strict `issues:`/`label:`/`milestone:` invocation grammar, the interactive picker, and fetching. The selected issues' title/body/labels seed this interview; record the selection as `source_issues`, persisted at initialization alongside `interview_output`. If `gh`/remote/issues are absent, skip silently and run the normal description interview. Not offered for `new_app`.
```

- [ ] **Step 2: Note `source_issues` in the persistence bullet**

In the bullet beginning "The approved interview output … becomes `interview_output`, persisted to `state.json` at initialization", append:
```markdown
 For issue-driven `feature_addition` runs, `source_issues` is persisted at the same point (see `issue-driven-runs.md` and `state-schema.md`).
```

- [ ] **Step 3: Verify**

Run: `grep -n "issue-driven-runs\|source_issues\|GitHub Issues" skills/ios-genesis/references/orchestration-flow.md`
Expected: the new Step 0 bullet + the persistence note reference the doc and field.

- [ ] **Step 4: Commit**

```bash
git add skills/ios-genesis/references/orchestration-flow.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "orchestration-flow: Step 0 issue selection + seeding"
```

## Chunk 2: Output side — closing, developer PR body, wiring, version, validation

### Task 4: Add the `Closes #N` drop + injection to `pr-review-flow.md`

**Files:**
- Modify: `skills/ios-genesis/references/pr-review-flow.md` (`## pr_creation` section, around the `pr_description_context` bullet ~line 16)

- [ ] **Step 1: Add the pre-dispatch drop + injection to `pr_creation`**

In `## pr_creation`, immediately after the `pr_description_context:` bullet (line 16), add:
```markdown
- **Issue-driven runs (`source_issues` non-empty):** *before* dispatching `create_pr`, present the `Closes #N` list (default: every issue in `source_issues`) via `AskUserQuestion` and let the user drop any issue whose work isn't complete. Append a `Closes #N` line per retained issue to `pr_description_context`; the developer reproduces these trailers verbatim in the PR **body** (see `agents/ios-developer.md`). Putting the keyword in the PR description — not a commit message — is required because `merge` squash-merges (which rewrites commits); only the body keyword triggers GitHub's auto-close on merge. Dropped issues get no `Closes` line and stay open (no comment). If `source_issues` is empty or unset, this step is a no-op. The `merge` phase itself is unchanged. See `issue-driven-runs.md`.
```

- [ ] **Step 2: Verify**

Run: `grep -n "Closes #N\|source_issues\|issue-driven-runs" skills/ios-genesis/references/pr-review-flow.md`
Expected: the new bullet references the keyword, the state field, and the doc.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/pr-review-flow.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "pr-review-flow: Closes #N drop + inject into pr_description_context"
```

### Task 5: Make `ios-developer.md` reproduce `Closes #N` verbatim

**Files:**
- Modify: `agents/ios-developer.md` (`## dispatch_type: create_pr`, step "Open a PR via `gh pr create`" ~line 109)

- [ ] **Step 1: Add the verbatim-trailer instruction**

On the `create_pr` step that reads "Open a PR via `gh pr create`, with a title summarizing the change and a body built from `pr_description_context` (reference `docs/architecture.md` and `docs/design.md` if they exist).", append this sentence:
```markdown
 If `pr_description_context` contains any `Closes #N` trailer lines, reproduce them **verbatim** on their own lines at the end of the PR body — do not paraphrase or summarize them, since GitHub only auto-closes the referenced issues when the exact `Closes #N` keyword appears in the PR description.
```

- [ ] **Step 2: Verify**

Run: `grep -n "Closes #N" agents/ios-developer.md`
Expected: one hit in the `create_pr` step.

- [ ] **Step 3: Commit**

```bash
git add agents/ios-developer.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "ios-developer: reproduce Closes #N trailers verbatim in PR body"
```

### Task 6: Report auto-close in the `pr_creation` checkpoint summary

**Files:**
- Modify: `skills/ios-genesis/references/checkpoints.md` (step 5, the `visual_verification`/phase-summary bullet ~line 51)

- [ ] **Step 1: Add a pr_creation auto-close note to step 5**

In `## 5. Present the summary to the user`, within the bullet that describes per-phase summaries, add a sentence covering `pr_creation`:
```markdown
For `pr_creation` on an issue-driven run, the summary also lists which issues the PR will auto-close on merge (the retained `Closes #N` set); the drop decision itself happens *before* the `create_pr` dispatch (see `pr-review-flow.md`), not at this checkpoint.
```

- [ ] **Step 2: Verify**

Run: `grep -n "auto-close\|Closes #N" skills/ios-genesis/references/checkpoints.md`
Expected: the new sentence present.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/references/checkpoints.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "checkpoints: pr_creation reports issues to auto-close"
```

### Task 7: Reference the new doc in `SKILL.md`

**Files:**
- Modify: `skills/ios-genesis/SKILL.md` (`## Reference docs` list ~lines 21-27)

- [ ] **Step 1: Add the list entry**

After the `references/pr-review-flow.md` line, add:
```markdown
- `references/issue-driven-runs.md` - consuming selected GitHub Issues as `feature_addition` input and closing them on merge (feature_addition only)
```

- [ ] **Step 2: Verify**

Run: `grep -n "issue-driven-runs.md" skills/ios-genesis/SKILL.md`
Expected: one hit in the Reference docs list.

- [ ] **Step 3: Commit**

```bash
git add skills/ios-genesis/SKILL.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "SKILL: reference issue-driven-runs doc"
```

### Task 8: Document issue-driven runs in `README.md`

**Files:**
- Modify: `README.md` (in the `### Usage` section, after the three bullets describing New app / Feature addition / Resume ~line 100)

- [ ] **Step 1: Add a short subsection**

After the Resume bullet in `### Usage`, add:
```markdown

**Issue-driven runs (feature addition).** When you point a feature-addition run at a project whose GitHub repo has open Issues (and `gh` is authenticated), Step 0 offers to build the run from selected Issues instead of a typed description: it lists your open issues to pick from, or you can name them in the invocation (`issues:12,13,14`, `label:bug`, or `milestone:v1.0.1`). The picked issues seed the requirements interview, and the run's PR gets `Closes #N` for them (reviewed before the PR is opened), so they close automatically when it merges. If `gh` isn't set up or the repo has no issues, runs work exactly as before.
```

- [ ] **Step 2: Verify**

Run: `grep -n "Issue-driven runs\|issues:12,13,14\|Closes #N" README.md`
Expected: the new subsection present.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "README: document issue-driven runs"
```

### Task 9: Bump plugin version to 0.4.0

**Files:**
- Modify: `.claude-plugin/plugin.json` (`"version"` field)

- [ ] **Step 1: Bump the version**

Change `"version": "0.3.1"` to `"version": "0.4.0"`.

- [ ] **Step 2: Verify**

Run: `grep '"version"' .claude-plugin/plugin.json`
Expected: `"version": "0.4.0"`.

- [ ] **Step 3: Commit**

```bash
git add .claude-plugin/plugin.json
git -c user.name="Claude Fable 5" -c user.email="noreply@anthropic.com" commit -m "Bump plugin to 0.4.0 (issue-driven runs)"
```

### Task 10: Manual end-to-end validation

**No file changes** — this is a manual run, driven by Giorgia (the plugin is validated by real runs, not automated tests). Cadenza (`~/Projects/scratch/Cadenza`, a `feature_addition` target whose GitHub repo can hold the backlog issues) is the natural candidate.

- [ ] **Step 1: Reinstall the 0.4.0 plugin** (the version-bump/cache dance)

```
/plugin marketplace update ios-orchestrator
/plugin uninstall ios-genesis@ios-orchestrator
/plugin install ios-genesis@ios-orchestrator
```
Restart the session; run `/plugin` and confirm it reads **0.4.0**.

- [ ] **Step 2: Picker path** — with ≥2 open issues on the repo and `gh` authed, run `/ios-genesis <path>` (no issue shortcut). Confirm Step 0 offers the "work from issues?" picker, the picked issues seed the interview (terse issues get clarified), and after init `state.json` contains `source_issues`.

- [ ] **Step 3: Shortcut path** — run `/ios-genesis <path> issues:<n>,<m>`. Confirm the picker is skipped and only those issues are used; a nonexistent number is warned-and-skipped.

- [ ] **Step 4: Closing + drop** — carry a run to `pr_creation`. Confirm the pre-`create_pr` drop prompt appears; drop one issue; confirm the PR body has `Closes #N` for the retained issues (verbatim) and none for the dropped one. Merge and confirm the retained issues auto-close and the dropped one stays open.

- [ ] **Step 5: Graceful absence** — run against a repo with no GitHub remote (or with `gh` unauthed). Confirm the issue path is silently skipped and the normal description flow runs unchanged, with no `source_issues` and no `Closes` lines.

- [ ] **Step 6: Resume** — stop a run after Step 0, then resume. Confirm `source_issues` survives and pr_creation still closes them.

- [ ] **Step 7: Scope check** — confirm the diff touched only `skills/ios-genesis/**`, `agents/ios-developer.md`, `README.md`, and `.claude-plugin/plugin.json` — no Swift, no new agent files.

---

## Execution notes

- Commit after each task (frequent commits). All commits authored as `Claude Fable 5` per repo convention.
- After Chunk 1 and Chunk 2, run the plan-document-reviewer loop before execution handoff.
- When ready to ship: open a PR from `feature/issue-driven-runs` to `main`, then Giorgia runs the reinstall dance (Task 10 Step 1) to receive 0.4.0.
