# Context Contract

How the orchestrator and subagents move context so that no agent ever loads the whole project. The governing principle: **never let an agent explore — make exploration unnecessary by giving it a cheap map and a precise way to jump.** The orchestrator carries *handles* (file paths + section anchors), never file or doc bodies; each worker opens with exactly its slice loaded.

This doc is the canonical description of the scheme; `SKILL.md`, `orchestration-flow.md`, `state-schema.md`, `checkpoints.md`, and the agent prompts point here instead of restating it. Load it as needed.

## Repo map (symbols.txt)

A compact symbol index the orchestrator generates so workers and the Context Scout can jump to a declaration instead of listing directories.

- **Generation** (run by the orchestrator, never an agent):

  ```bash
  grep -rn -E "^\s*(public |internal |private |fileprivate |final |open )*(class|struct|enum|protocol|actor|extension) " \
    --include="*.swift" <sources-root> | sed 's/ *{.*//'
  ```

  One line per declared type as `path:line: <decl>` — a few thousand tokens even for a large app.

- **When:** regenerated at each phase start (before that phase's first wave) and after each wave-end integration build (so it reflects code the wave just wrote). Rides the existing build-serial rhythm — see `orchestration-flow.md`.
- **Where:** `.ios-orchestrator/symbols.txt` — gitignored, ephemeral, scope-check-exempt like `state.json`.
- **Mode dependence:** meaningful only once code exists. `feature_addition` has it from the first phase (existing codebase). `new_app` has nothing to index until `foundation` builds; the earliest greenfield writes work from `docs/architecture.md` (which *is* the map for them), and `symbols.txt` populates from the foundation wave onward for `integration`, `test_engineer`, `visual_verification`, and `code_review`.

## Context Scout

A cheap `model: haiku` agent (`agents/ios-context-scout.md`) that replaces a worker's exploration phase with a precomputed set of handles.

- **Input (dispatch prompt):** the task's scope text or a `scope.md#<section>` ref, the worker's `owned_files`, and the contents of `symbols.txt`. **No Swift bodies.**
- **Output (report):** a JSON block of handles, never contents:

  ```json
  { "files": [ { "path": "App/Views/Home/HomeView.swift", "ranges": [[42, 88]], "reason": "the modifier the task changes" } ] }
  ```

- **Gate — reads-existing-code dispatches only.** Run the Scout before: every `feature_addition` worker; `test_engineer` (reads `source_files`); `code_review`; `integration` (reads siblings' outputs); and `address_visual`/`address_review` re-dispatches. **Skip** it for `new_app` greenfield `foundation`/`screen` writes — there is nothing to scope. (A future second gate — only when candidate files exceed ~300 lines — is possible but not built.)
- **Orchestration:** the orchestrator dispatches the Scout first, then injects its `files`/`ranges` into the worker's dispatch as an explicit block:

  > **Load exactly these ranges** (from the Context Scout); do not explore beyond them without cause:
  > - `App/Views/Home/HomeView.swift:42-88` — the modifier the task changes

  The worker still runs its own `Read` calls (it starts cold), but guided — no discovery round-trips at the expensive tier.
- **Cost note:** the Scout adds one Haiku dispatch before each scoped worker. On a change touching a single small file the overhead can exceed the saving; the reads-existing-code gate keeps it off cases where it would not pay.

## Refs-not-bodies dispatch contract

The core rule: **every dispatch carries handles + minimal state, not bodies.**

- `architecture_summary`/`design_summary` are passed as **refs** — `docs/architecture.md#<Module>`, `docs/design.md#<Screen>`, or `.ios-orchestrator/scope.md#<section>` — never the text.
- For `feature_addition`, the Architect writes its scope to gitignored `.ios-orchestrator/scope.md` with `## <section>` anchors instead of returning the body; `state.json`'s `architecture_summary` becomes a pointer to it (see `state-schema.md`). Because `.ios-orchestrator/` is gitignored and ephemeral, this is not a stale artifact in the shipped repo — the original reason feature additions wrote no file.
- `docs/architecture.md` and `docs/design.md` use stable section anchors (`## <ModuleName>`, `## <ScreenName>` — the canonical screen names screens already register under) so `path#anchor` addressing is reliable.
- **Orchestrator invariant:** the orchestrator holds **zero** file/doc bodies in its own context. It reads only control fields (task graph, statuses, refs). When a checkpoint must surface a doc's content (`checkpoints.md` step 5), it reads that one section *at checkpoint time* rather than holding the body throughout.

## Search before read

A hard rule in every worker agent prompt:

> Before reading a file, `grep -n` for the symbol/string you need, then `Read` with `offset`/`limit` around the hits. Never read a file over ~300 lines in full. When your dispatch includes a "Load exactly these ranges" block (from the Context Scout), start there and do not explore beyond it without cause.

The Scout's ranges are a floor, not a ceiling — this keeps even un-scouted reads (e.g. a greenfield screen writer glancing at a foundation output) narrow.

## Deny list

Files never worth their token cost, kept behind deny rules rather than model discretion:

- `**/*.pbxproj` (20k+ tokens alone), `**/Package.resolved`, `**/*.xcodeproj/**`, `**/Pods/**`, `**/DerivedData/**`, `**/__Snapshots__/**`, generated API clients, and non-base localized `*.strings` (`*/*.lproj/*.strings` except `Base.lproj`/`en.lproj`).

**Delivery:** if a Claude Code plugin can ship permission/deny rules (bundled settings), they are shipped so protection is automatic on install. If not, the README documents a one-time `settings.json` snippet and the worker prompts carry a belt-and-suspenders instruction never to read these paths. The chosen path is recorded here at implementation.

## Validation

Token savings cannot be unit-tested. The scheme is validated by a real `feature_addition` run (Cadenza's backlog is the natural target) confirming: dispatches carry refs not bodies; workers load only Scout ranges and never list directories or read whole large files; no worker reads a denied path; the orchestrator's own context never contains Swift/doc bodies; and end-to-end output is identical to a v0.6.0 run of the same change (this is a plumbing change, not a behavior change).
