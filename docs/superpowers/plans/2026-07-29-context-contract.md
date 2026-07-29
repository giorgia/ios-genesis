# Context Contract (v0.7.0) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ios-genesis subagents load only their relevant slice of the project — the orchestrator carries handles, workers open with exactly their ranges — instead of re-shipping full doc bodies and exploring cold.

**Architecture:** Five coordinated changes to the plugin's docs/agent prompts (no Swift): a gitignored repo map (`symbols.txt`) regenerated on the orchestrator's build rhythm; a new `model: haiku` Context Scout that returns file+line-range handles for reads-existing-code dispatches; a refs-not-bodies dispatch contract (architecture/design/scope passed as `path#anchor`, feature_addition scope moved to gitignored `.ios-orchestrator/scope.md`); a hard search-before-read rule in every worker; and a deny list for expensive files.

**Tech Stack:** Markdown skill/agent/reference docs; Claude Code plugin manifest; `grep`-based verification (no test runner — these are doc edits).

**Spec:** `docs/superpowers/specs/2026-07-29-context-contract-design.md`

**Base branch:** stacks on v0.6.0 (`feature/quick-fix-lane`, PR #10) since the refs-not-bodies contract builds on the quick lane's dispatch changes. New branch `feature/context-contract` off that tip (or off `main` once #10 merges).

**Convention reminders:** commits authored as `Claude Fable 5 <noreply@anthropic.com>`, no Co-Authored-By trailer. `.ios-orchestrator/` is gitignored and scope-check-exempt. Reference docs are loaded on demand (`SKILL.md` "load as needed"), so new docs add zero cost to runs that don't touch them.

---

## Chunk 1: Foundations — repo map, Scout agent, canonical doc

### Task 1: Canonical reference doc `references/context-contract.md`

**Files:**
- Create: `skills/ios-genesis/references/context-contract.md`

- [ ] **Step 1: Write the reference doc.** Cover, in this order, five sections with these headings: `## Repo map (symbols.txt)`, `## Context Scout`, `## Refs-not-bodies dispatch contract`, `## Search before read`, `## Deny list`. Content per the spec §1–§5. Include the exact `symbols.txt` grep, the Scout JSON output shape (`{files:[{path,ranges,reason}]}`), the reads-existing-code gate list, the "load exactly these ranges" injection block wording, and the deny globs. State the orchestrator invariant: zero file/doc bodies in the orchestrator's own context.

- [ ] **Step 2: Verify structure.**

Run: `grep -c '^## ' skills/ios-genesis/references/context-contract.md`
Expected: `5`

Run: `grep -n 'symbols.txt\|handles, never contents\|Load exactly these ranges' skills/ios-genesis/references/context-contract.md`
Expected: at least 3 hits.

- [ ] **Step 3: Commit.**

```bash
git add skills/ios-genesis/references/context-contract.md
git commit -m "docs(context): add context-contract reference doc"
```

### Task 2: Context Scout agent `agents/ios-context-scout.md`

**Files:**
- Create: `agents/ios-context-scout.md`

- [ ] **Step 1: Write the agent.** Frontmatter: `name: ios-context-scout`, a one-line `description`, `tools: Read, Grep, Glob`, `model: haiku`. Body: role = given a task's scope/ref + `owned_files` + `symbols.txt`, return the exact files and line ranges the worker should load. Input section (what the dispatch provides — scope text or `scope.md#section` ref, `owned_files`, `symbols.txt` contents; **no Swift bodies**). Method: consult `symbols.txt` first; do at most a few narrow `grep -n`/`Read offset/limit` to resolve ranges. Output: a fenced JSON report block `{ "files": [ { "path": "...", "ranges": [[start,end]], "reason": "..." } ] }`. Role boundary: **returns handles, never file contents**; writes nothing.

- [ ] **Step 2: Verify.**

Run: `grep -n 'model: haiku\|tools: Read, Grep, Glob\|handles, never' agents/ios-context-scout.md`
Expected: all three present.

Run: `grep -c 'ranges' agents/ios-context-scout.md`
Expected: ≥2.

- [ ] **Step 3: Commit.**

```bash
git add agents/ios-context-scout.md
git commit -m "feat(agent): add ios-context-scout (haiku scoping pass)"
```

### Task 3: Wire `symbols.txt` generation into the orchestration docs

**Files:**
- Modify: `skills/ios-genesis/references/orchestration-flow.md` (Task graph and waves / Fan-out mechanics — the wave-end integration build steps)
- Modify: `skills/ios-genesis/references/state-schema.md` (Initialization / field notes — document the `.ios-orchestrator/symbols.txt` and `.ios-orchestrator/scope.md` locations)

- [ ] **Step 1: orchestration-flow.md.** In the developer wave-end integration-build step (`### developer — write in parallel, build as integration`, the "Wave-end integration build" bullet) add: after the wave-end `xcodebuild build`, regenerate `.ios-orchestrator/symbols.txt` (the grep from `context-contract.md`). Also add, at phase start in "Task graph and waves", a line: the orchestrator (re)generates `symbols.txt` before dispatching a phase's first wave when code exists (feature_addition always; new_app from the foundation wave onward). Point to `context-contract.md` for the command.

- [ ] **Step 2: state-schema.md.** In the Initialization section (near the `.gitignore`/`.ios-orchestrator/` note) add one line documenting `.ios-orchestrator/symbols.txt` (repo map, regenerated by the orchestrator, gitignored, ephemeral) and `.ios-orchestrator/scope.md` (feature_addition scope artifact — see Task 5/7). Both are scope-check-exempt like `state.json`.

- [ ] **Step 3: Verify.**

Run: `grep -rn 'symbols.txt' skills/ios-genesis/references/orchestration-flow.md skills/ios-genesis/references/state-schema.md`
Expected: ≥2 hits (both files).

- [ ] **Step 4: Commit.**

```bash
git add skills/ios-genesis/references/orchestration-flow.md skills/ios-genesis/references/state-schema.md
git commit -m "docs(context): regenerate symbols.txt on the build rhythm"
```

---

## Chunk 2: Refs-not-bodies dispatch contract

### Task 4: SKILL.md contract change

**Files:**
- Modify: `skills/ios-genesis/SKILL.md` (the Notes section, current line ~49; the reference-docs list)

- [ ] **Step 1: Rewrite the "every dispatch must include all context" note.** Replace it with: *"every dispatch includes the handles (file paths + section anchors) and minimal state the subagent needs; the subagent reads its own slice. Never embed file or doc bodies in a dispatch or in the orchestrator's own reasoning (the orchestrator carries handles, not bodies). See `references/context-contract.md`."* Keep the "fan-out dispatches carry all context they need" idea but reframed as handles.

- [ ] **Step 2: Add the Scout step.** In the Notes (or a new line in the top-level control flow step 4), state: before dispatching a reads-existing-code worker (feature_addition workers, `test_engineer`, `code_review`, `integration`, `address_visual`/`address_review`), dispatch `ios-context-scout` first and inject its returned ranges into the worker dispatch as a "Load exactly these ranges" block. Greenfield `foundation`/`screen` writes are not scouted.

- [ ] **Step 3: List the new reference doc.** Add `references/context-contract.md` to the "Reference docs" list with a one-line description.

- [ ] **Step 4: Verify.**

Run: `grep -n 'context-contract.md\|carries handles\|Load exactly these ranges\|ios-context-scout' skills/ios-genesis/SKILL.md`
Expected: all four present.

Run: `grep -n 'must include all context' skills/ios-genesis/SKILL.md`
Expected: no hits (old wording gone).

- [ ] **Step 5: Commit.**

```bash
git add skills/ios-genesis/SKILL.md
git commit -m "docs(context): refs-not-bodies dispatch contract + Scout step"
```

### Task 5: Architect writes scope to `.ios-orchestrator/scope.md` + section anchors

**Files:**
- Modify: `agents/ios-architect.md` (Feature addition section; New app architecture.md structure)

- [ ] **Step 1: feature_addition scope artifact.** Change the "Do NOT write a file for feature additions — return the scope summary directly" instruction: the Architect now writes the scope summary to `.ios-orchestrator/scope.md` with `## <section>` anchors (one per affected module/screen) and returns a short pointer + the section anchor list in its report (not the body). Note explicitly that `.ios-orchestrator/scope.md` is gitignored and ephemeral, so it is NOT a stale artifact in the shipped repo (that was the original reason for not writing a file). Add `Write` is already in tools — confirm frontmatter `tools:` includes Write (it does).

- [ ] **Step 2: new_app anchors.** In the `docs/architecture.md` structure template, require stable `## <ModuleName>` headings (already present) and add per-screen subsection anchors under `## Screens` so `docs/architecture.md#<Module>` addressing is stable.

- [ ] **Step 3: Verify.**

Run: `grep -n 'scope.md\|gitignored\|anchor' agents/ios-architect.md`
Expected: scope.md + gitignored present.

Run: `grep -n 'Do NOT write a file for feature additions — return the scope summary directly' agents/ios-architect.md`
Expected: no hits (old instruction replaced).

- [ ] **Step 4: Commit.**

```bash
git add agents/ios-architect.md
git commit -m "docs(context): architect writes scope.md with section anchors"
```

### Task 6: UI Designer canonical per-screen anchors

**Files:**
- Modify: `agents/ios-ui-designer.md`

- [ ] **Step 1: Make anchors the addressing contract.** State that each screen's design section uses a stable `## <ScreenName>` heading matching the canonical screen name (the same name it registers under in the router / `docs/design.md`), so dispatches can reference `docs/design.md#<ScreenName>`. If the designer already writes per-screen sections, make the heading convention explicit and canonical.

- [ ] **Step 2: Verify.**

Run: `grep -n 'ScreenName\|#<\|canonical' agents/ios-ui-designer.md`
Expected: canonical screen-name heading convention present.

- [ ] **Step 3: Commit.**

```bash
git add agents/ios-ui-designer.md
git commit -m "docs(context): canonical per-screen anchors in design.md"
```

### Task 7: state-schema — `architecture_summary` becomes a ref

**Files:**
- Modify: `skills/ios-genesis/references/state-schema.md` (the `architecture_summary` field reference)

- [ ] **Step 1: Redefine `architecture_summary`.** Change it from "the Architect's full scope-summary text" to "a pointer to `.ios-orchestrator/scope.md` (feature_addition) — the scope lives in that gitignored file with `## <section>` anchors, not inline in `state.json`. Later phases receive `scope.md#<section>` refs, not the body." Note the migration/back-compat: a pre-0.7.0 state file with inline `architecture_summary` text still works (readers accept either a ref or inline text); new runs write the ref.

- [ ] **Step 2: Verify.**

Run: `grep -n 'scope.md#\|pointer to\|pre-0.7.0' skills/ios-genesis/references/state-schema.md`
Expected: all present.

- [ ] **Step 3: Commit.**

```bash
git add skills/ios-genesis/references/state-schema.md
git commit -m "docs(context): architecture_summary is a ref to scope.md"
```

### Task 8: orchestration-flow — refs in dispatch inputs + Scout pre-dispatch

**Files:**
- Modify: `skills/ios-genesis/references/orchestration-flow.md` (phase dispatch descriptions in New app / Feature addition + Fan-out mechanics)

- [ ] **Step 1: Convert dispatch inputs to refs.** Wherever a phase dispatch lists `architecture_summary`/`design_summary` as inputs (New app steps 1–5, Feature addition steps 1–5, and the Fan-out mechanics per-phase dispatch prompt lists), change them to refs: `architecture_ref` (`docs/architecture.md#<Module>` or `.ios-orchestrator/scope.md#<section>`) and `design_ref` (`docs/design.md#<Screen>`). Do not embed bodies.

- [ ] **Step 2: Add the Scout pre-dispatch step.** In "Fan-out mechanics per phase" (and the solo/sequential path), add: for reads-existing-code dispatches, dispatch `ios-context-scout` first with the task scope + `owned_files` + `symbols.txt`, then inject its ranges into the worker dispatch. Reference `context-contract.md` for the gate list. Greenfield foundation/screen writes skip the Scout.

- [ ] **Step 3: Verify.**

Run: `grep -n 'architecture_ref\|design_ref\|ios-context-scout' skills/ios-genesis/references/orchestration-flow.md`
Expected: all three present.

Run: `grep -c 'architecture_summary\|design_summary' skills/ios-genesis/references/orchestration-flow.md`
Expected: `0` (all converted to refs) — OR, if any remain intentionally (e.g. describing state persistence), confirm each is deliberate.

- [ ] **Step 4: Commit.**

```bash
git add skills/ios-genesis/references/orchestration-flow.md
git commit -m "docs(context): dispatch inputs are refs; Scout pre-dispatch step"
```

### Task 9: checkpoints — surface content by reading the section at checkpoint time

**Files:**
- Modify: `skills/ios-genesis/references/checkpoints.md` (step 5, artifact content surfacing)

- [ ] **Step 1: Adjust content-surfacing.** In step 5, note that when a checkpoint must surface a doc's key content, the orchestrator reads the specific section (`docs/architecture.md#<Module>` / `docs/design.md#<Screen>` / `.ios-orchestrator/scope.md#<section>`) **at checkpoint time**, rather than holding the full body throughout the run — consistent with the orchestrator-carries-handles invariant (`context-contract.md`). Add a one-line note that `symbols.txt` is regenerated after wave-end builds (cross-ref Task 3).

- [ ] **Step 2: Verify.**

Run: `grep -n 'at checkpoint time\|context-contract.md\|handles' skills/ios-genesis/references/checkpoints.md`
Expected: present.

- [ ] **Step 3: Commit.**

```bash
git add skills/ios-genesis/references/checkpoints.md
git commit -m "docs(context): checkpoints read sections on demand, not held bodies"
```

---

## Chunk 3: Worker rules, deny list, release

### Task 10: Search-before-read + load-exact-ranges rule in every worker agent

**Files:**
- Modify: `agents/ios-developer.md`, `agents/ios-test-engineer.md`, `agents/ios-code-reviewer.md`, `agents/ios-visual-verifier.md`, `agents/ios-release-manager.md`

- [ ] **Step 1: Add the shared rule** to each worker agent (a `## Reading files` or "Context discipline" subsection). Text: *"Before reading a file, `grep -n` for the symbol/string you need, then `Read` with `offset`/`limit` around the hits. Never read a file over ~300 lines in full. When your dispatch includes a 'Load exactly these ranges' block (from the Context Scout), start there and do not explore beyond it without cause. See `references/context-contract.md`."* Keep wording identical across agents (DRY — same rule).

- [ ] **Step 2: Verify (all five).**

Run: `for f in ios-developer ios-test-engineer ios-code-reviewer ios-visual-verifier ios-release-manager; do grep -q 'Load exactly these ranges' agents/$f.md && echo "$f OK" || echo "$f MISSING"; done`
Expected: five `OK`.

- [ ] **Step 3: Commit.**

```bash
git add agents/ios-developer.md agents/ios-test-engineer.md agents/ios-code-reviewer.md agents/ios-visual-verifier.md agents/ios-release-manager.md
git commit -m "docs(context): search-before-read rule in all worker agents"
```

### Task 11: Deny list for expensive reads (feasibility-gated delivery)

**Files:**
- Investigate then Create/Modify: `.claude/settings.json` (if plugin-shippable) OR `README.md` install section (documented snippet)
- Modify: `skills/ios-genesis/references/context-contract.md` (record the chosen delivery)

- [ ] **Step 1: Confirm feasibility.** Determine whether a Claude Code plugin can ship permission/deny rules (bundled settings) that take effect on install. Check the plugin docs (context7 `mcp__plugin_context7_context7` for "claude code plugin settings permissions" or the Claude Code docs). Record the answer.

- [ ] **Step 2a (if plugin-shippable): ship the deny rules.** Add the deny globs from the spec §5 to the plugin's settings file. Verify the file is valid JSON.

- [ ] **Step 2b (if NOT shippable): document + prompt fallback.** Add a "Reduce token cost" install-step snippet to `README.md` with the deny globs for the user's `settings.json`, AND add a belt-and-suspenders line to the worker rule (Task 10 text) instructing workers never to read the deny-listed paths.

- [ ] **Step 3: Record the decision** in `context-contract.md`'s `## Deny list` section (which path was taken).

- [ ] **Step 4: Verify.**

Run: `grep -rn 'pbxproj\|DerivedData\|__Snapshots__' README.md .claude/settings.json skills/ios-genesis/references/context-contract.md 2>/dev/null`
Expected: the deny globs appear in whichever delivery file was chosen + context-contract.md.

- [ ] **Step 5: Commit.**

```bash
git add -A
git commit -m "feat(context): deny expensive reads (project.pbxproj, DerivedData, etc.)"
```

### Task 12: README + version bump

**Files:**
- Modify: `README.md` (new `## 0.7.0` section), `.claude-plugin/plugin.json`

- [ ] **Step 1: README section.** Add `## 0.7.0 — the context contract` before `## Field-tested`, in the voice of the existing version sections: the token problem (whole project shipped every dispatch), the fix (repo map + Haiku Scout + refs-not-bodies + search-before-read + deny list), and that it's a plumbing change with identical output. Note module-split is the deferred v0.8.0.

- [ ] **Step 2: Version bump.** `.claude-plugin/plugin.json` `"version": "0.6.0"` → `"0.7.0"`.

- [ ] **Step 3: Verify.**

Run: `grep -n '0.7.0' .claude-plugin/plugin.json README.md`
Expected: both present.

Run: `python3 -c "import json;print(json.load(open('.claude-plugin/plugin.json'))['version'])"`
Expected: `0.7.0`.

- [ ] **Step 4: Commit.**

```bash
git add README.md .claude-plugin/plugin.json
git commit -m "docs(context): README 0.7.0 section + version bump"
```

### Task 13: Final consistency sweep + validation checklist

**Files:**
- No new files — verification only; may touch any doc to fix a dangling reference.

- [ ] **Step 1: Cross-reference sweep.**

Run: `grep -rl 'context-contract\|ios-context-scout\|symbols.txt\|scope.md' skills agents README.md`
Expected: the doc set is internally consistent (SKILL.md, orchestration-flow, state-schema, checkpoints, context-contract, the worker agents, architect).

Run: `grep -rn 'must include all context\|architecture_summary.*full.*text' skills agents`
Expected: no stale pre-0.7.0 wording remains.

- [ ] **Step 2: JSON validity.**

Run: `python3 -c "import json;json.load(open('.claude-plugin/plugin.json'));[json.load(open(p)) for p in ['.claude/settings.json'] if __import__('os').path.exists(p)];print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Write the validation checklist** into the spec's §8 or a short `## Validation` note at the end of `context-contract.md`: the manual `feature_addition` run (Cadenza backlog) asserting (a) dispatches carry refs not bodies, (b) workers load only Scout ranges, (c) no denied path is read, (d) orchestrator context holds no Swift/doc bodies, (e) output identical to a v0.6.0 run.

- [ ] **Step 4: Commit.**

```bash
git add -A
git commit -m "docs(context): consistency sweep + validation checklist"
```

---

## Execution notes

- **No test runner:** these are doc/prompt edits; "verification" is the grep assertions in each task. The real test is the manual validation run (Task 13 / spec §8) — it cannot be automated here.
- **Ordering:** Chunk 1 (foundations) before Chunk 2 (which references the Scout and context-contract doc) before Chunk 3 (worker rules + release). Within a chunk, tasks are mostly independent but committed separately.
- **Blast radius:** Task 4 (SKILL.md contract) and Task 8 (orchestration-flow refs) are the load-bearing changes — review these most carefully, since every phase reads them.
