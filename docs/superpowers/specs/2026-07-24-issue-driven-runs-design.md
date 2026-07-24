# ios-genesis v0.4.0 — Issue-Driven Runs

## Problem

Today `/ios-genesis` takes a single free-text description and produces a PR. It has no relationship to a backlog: it never reads what the user has already written down as GitHub Issues, and never closes anything when its work merges. A user with a real backlog (e.g. Cadenza's post-review bug + feature list) has to hand-copy each item into a run description and manually close the issue afterward. The tool builds features but doesn't participate in the track → work → close loop.

This feature lets a `feature_addition` run **consume selected GitHub Issues as its requirements input** and **close them when its PR merges** — reading and closing only. It deliberately does NOT create, triage, or prioritize issues (deferred — see §7).

## Decisions made during brainstorming

- **Scope: issue-driven runs only** — read selected issues in, close them on merge. Issue creation/triage and a full backlog-runner mode are out of scope (§7).
- **Selection: interactive pick + shortcuts.** At Step 0 the orchestrator lists open issues via `AskUserQuestion` for the user to select; if the invocation already named issues (numbers or a label/milestone), those are used directly and the picker is skipped.
- **Issues seed the interview.** Fetched issue title/body/labels become the input to the existing Step 0 interview, which can clarify terse issues before the architect scopes them. Issues are a new *source* for `interview_output`; everything downstream is unchanged. No per-issue→task mapping.
- **Closing: `Closes #N`, reviewed at the PR checkpoint.** The pr_creation PR body lists `Closes #N` for the run's issues (default all); the checkpoint lets the user drop any not actually finished. GitHub's native auto-close fires on merge. Dropped issues stay open.
- **`feature_addition` only, gated on `gh` + a GitHub remote.** `new_app` has no issues to consume. When `gh` is absent/unauthed or there is no GitHub remote or no open issues, the issue path is silently unavailable and the run falls back to the normal description flow — never an error.
- **Ships as v0.4.0.** The parked interactive-flow-verification design moves to a later version (0.5.0).

## 1. Trigger & issue selection (Step 0)

Runs only for `mode: feature_addition` against a repo with a GitHub remote.

- **Gating detection:** confirm `gh` is available and authed (`gh auth status`) and the repo has a GitHub remote (`gh repo view` succeeds). If any check fails, do not offer the issue path; proceed with the normal free-text description interview. No error, no risk — the offer simply isn't shown (mirrors how `design-mode.md` omits Figma when its MCP is absent).
- **Selection:**
  - **Invocation shortcut (strict grammar, no prose scanning):** the description argument is treated as an issue shortcut *only* when it begins with one of these exact tokens: `issues:` followed by numbers (`issues:12,13,14`), `label:<name>`, or `milestone:<name>`. Exactly one token is honored per invocation — tokens do not combine (`label:bug milestone:v1` is not supported in v0.4.0; the implementing doc states single-token-only explicitly). Anything else — including free text that merely contains a `#` (e.g. "fix the #1 priority crash") — is treated as a normal free-text description, and the picker path below runs. This explicit grammar removes any ambiguity between an issue reference and ordinary prose.
  - **Interactive picker (default):** when no shortcut token is present, run `gh issue list --state open --json number,title,labels`. If it returns any issues, ask via `AskUserQuestion` (multi-select): *"Work from existing issues, or describe fresh?"* — options are the open issues plus a "No — describe fresh" escape that drops to the normal description flow. If there are no open issues, skip silently to the normal flow.
- **Fetch selected issues:** `gh issue view <n> --json number,title,body,labels,url,comments` for each. Comments are always fetched and passed to the interview, which uses them as available (no length heuristic — fetching unconditionally is simpler and avoids a magic threshold).
- **Persist:** the selected issues are recorded in `source_issues` (see §4). Because Step 0 for `feature_addition` runs *before* `state.json` exists, `source_issues` is written at **state initialization**, alongside `interview_output` (see `state-schema.md`'s Initialization section) — not as a separate pre-interview write. This is the same timing as `interview_output`/`design_sources`, and it makes the selection survive resume and reach pr_creation. Between the picker (during Step 0) and the init write, the selection is held in-session, identical to how `interview_output` is held before it is persisted; a run interrupted in that small window re-selects on restart, exactly as it would re-run the interview.

## 2. Issues seed the interview

- The fetched issues' `title` + `body` + `labels` (and any pulled comments) are concatenated into the starting material for the existing Step 0 interview, in place of the `<description>` argument.
- The interview runs exactly as today (it already uses the superpowers brainstorming skill): the orchestrator may ask the user to clarify terse or ambiguous issues before producing the approved `interview_output`. `interview_output` states which issue numbers it covers.
- **Downstream is unchanged.** The architect scopes a task graph from `interview_output` as always; there is no issue→task mapping and no new per-task field. Issues influence the run purely through `interview_output` and `source_issues`.

## 3. Closing the loop (pr_creation)

The `Closes #N` list must land in the PR **body**, and the user's drop decision must happen **before** the PR is created (the developer's `create_pr` dispatch builds and pushes the body, and the standard checkpoint fires only *after* the PR already exists — so a post-hoc drop would require editing an already-pushed PR, which we avoid).

- **Before dispatching `create_pr`:** when `source_issues` is non-empty, the orchestrator presents the close-list (default: all of them) via `AskUserQuestion` and lets the user drop any issue whose work isn't actually complete.
- **Injection:** the resulting final list is passed into the `create_pr` dispatch as part of `pr_description_context` (see `pr-review-flow.md`), and the ios-developer writes a `Closes #N` line per retained issue into the PR **body**. Putting the keyword in the PR description (not a commit message) is required because the `merge` phase squash-merges, which rewrites commits — only the PR-body keyword reliably triggers auto-close.
- **Auto-close:** GitHub closes the referenced issues natively when the PR merges to the default branch. The existing `merge` phase (`gh pr merge --squash`) is unchanged and adds no closing logic — the keyword in the body is the sole mechanism. If the run stops before merge, nothing is closed.
- **Dropped issues** get no `Closes` line and stay open; no comment is posted (a partial-completion auto-comment is deferred — §8).
- If `source_issues` is empty (the run fell back to a description), no `Closes` lines are added and this step is a no-op — pr_creation behaves exactly as today.

## 4. State schema

`references/state-schema.md` gains one field:

- `source_issues`: list of `{ "number": int, "title": string, "url": string }` for the issues a run is built from. Present only for issue-driven `feature_addition` runs; **unset (key omitted)** otherwise, per the schema's existing convention.
- Written **at initialization** (added to the Initialization enumeration in `state-schema.md`, alongside `interview_output` and `design_sources`), from the Step 0 selection. Read before the `create_pr` dispatch to build the `Closes #N` list (§3). Carried through resume unchanged — a resumed run still closes its issues even in a later session.

## 5. Checkpoint presentation

- Step 0 interview presentation (documented in `issue-driven-runs.md`, not the post-phase `checkpoints.md` procedure, which has no Step 0 step): when issues seeded the run, the summary lists the selected issue numbers/titles and notes any that were named-but-skipped (nonexistent/already-closed).
- The `Closes #N` drop decision is an `AskUserQuestion` that runs *before* the `create_pr` dispatch (§3), not at the post-phase checkpoint. The standard pr_creation checkpoint (which fires after the PR exists) simply reports, in its summary, which issues the PR will auto-close on merge. Existing PR-summary content is otherwise unchanged.

## 6. Error handling & gating (all soft-fail)

- No `gh` / not authed / no GitHub remote / no open issues → issue path unavailable, normal description flow, no error.
- `gh issue view` fails on a selected issue → surface the error; offer retry or skip that issue; never abort the run.
- A named issue number that doesn't exist or is already closed → warn and skip it, note it in the Step 0 summary.
- pr_creation with empty `source_issues` → no `Closes` lines; identical to today.

## 7. Affected documents

- `skills/ios-genesis/references/issue-driven-runs.md` — **new**; gating detection, `gh` commands, selection UX, interview seeding, the Step 0 issue summary, soft-fail error handling (§6), and closing rules.
- `skills/ios-genesis/references/orchestration-flow.md` — Step 0 gains: detect remote+`gh` → offer/fetch issues → seed interview → persist `source_issues`.
- `skills/ios-genesis/references/state-schema.md` — `source_issues` field definition **plus** adding `source_issues` to the Initialization enumeration (written at init, alongside `interview_output`/`design_sources`).
- `skills/ios-genesis/references/checkpoints.md` — pr_creation checkpoint summary reports which issues will auto-close on merge (the drop decision itself is pre-`create_pr`, §3/§5). The Step 0 issue summary lives in `issue-driven-runs.md`/`orchestration-flow.md`, not here.
- `skills/ios-genesis/references/pr-review-flow.md` — the pre-`create_pr` `Closes #N` drop `AskUserQuestion`, and adding the retained `Closes #N` list to `pr_description_context` so the developer writes it into the PR body. The `merge` step is unchanged.
- `agents/ios-developer.md` — the `create_pr` instructions (currently "a body built from `pr_description_context`") gain one line: if `pr_description_context` contains `Closes #N` trailer lines, reproduce them **verbatim** at the end of the PR body, since GitHub only auto-closes on the exact keyword. (This is the sole agent-file edit; no new agents.)
- `skills/ios-genesis/SKILL.md` — reference the new doc under Reference docs.
- `README.md` — document issue-driven runs.
- `.claude-plugin/plugin.json` — version bump to `0.4.0`.

## 8. Deferred (explicitly out of scope for v0.4.0)

- **Issue creation / triage** — turning a brain-dump into tracked, labeled, sized issues (brainstorming scope option 2).
- **Full backlog-runner mode** — list → prioritize → pick → run → close → repeat autonomy (scope option 3).
- **Per-issue → task mapping** and richer partial-completion auto-comments; v0.4.0 closes at whole-run granularity with a human veto.
- **Non-GitHub trackers** (Jira/Linear/etc.).
- **`new_app` issue support** — there are no issues to consume at project creation.

## Validation plan

- `feature_addition` on a GitHub repo with open issues, `gh` authed: confirm Step 0 offers the picker, selected issues seed the interview (terse issues get clarified), `source_issues` persists, and the pr_creation PR body carries `Closes #N` for the chosen issues; verify merge auto-closes them.
- Same run, drop one issue at the pr_creation checkpoint: confirm the dropped issue gets no `Closes` line and remains open after merge.
- Invocation naming explicit issue numbers: confirm the picker is skipped and only those issues are used; a nonexistent number is warned-and-skipped.
- No GitHub remote (or `gh` unauthed): confirm the issue path is silently absent and the normal description flow runs unchanged.
- Resume an issue-driven run after Step 0: confirm `source_issues` survives and pr_creation still closes them.
- No-remote interaction: confirm the §1 gating (issue path requires an existing GitHub remote) means an issue-driven run can never reach pr_creation's "create a repo?" checkpoint — the issues live on an origin that already exists, so the new-repo path (whose fresh repo wouldn't contain those issue numbers) cannot co-occur. This is prevented by construction, not handled at pr_creation.
- Scope check: the feature touches only orchestrator references/docs + `plugin.json`; no new agent files required (the orchestrator drives `gh`, consistent with the existing repo/PR flow).
