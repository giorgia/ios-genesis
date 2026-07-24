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
  - If the invocation named issues — explicit numbers (`#12 #13` / `12,13`) or a `label:`/`milestone:` qualifier — fetch those directly and skip the picker.
  - Otherwise run `gh issue list --state open --json number,title,labels`. If it returns any issues, ask via `AskUserQuestion` (multi-select): *"Work from existing issues, or describe fresh?"* — options are the open issues plus a "No — describe fresh" escape that drops to the normal description flow. If there are no open issues, skip silently to the normal flow.
- **Fetch selected issues:** `gh issue view <n> --json number,title,body,labels,url,comments` for each. Comments are included only when the body is short/terse (heuristic: pull comments to give the interview more to clarify from).
- **Persist:** write `source_issues` to `state.json` (see §4) before the interview proceeds, so the selection survives resume and reaches pr_creation.

## 2. Issues seed the interview

- The fetched issues' `title` + `body` + `labels` (and any pulled comments) are concatenated into the starting material for the existing Step 0 interview, in place of the `<description>` argument.
- The interview runs exactly as today (it already uses the superpowers brainstorming skill): the orchestrator may ask the user to clarify terse or ambiguous issues before producing the approved `interview_output`. `interview_output` states which issue numbers it covers.
- **Downstream is unchanged.** The architect scopes a task graph from `interview_output` as always; there is no issue→task mapping and no new per-task field. Issues influence the run purely through `interview_output` and `source_issues`.

## 3. Closing the loop (pr_creation)

- At `pr_creation`, the orchestrator appends a `Closes #N` line to the PR body for each issue in `source_issues` (default: all of them).
- The pr_creation checkpoint (`checkpoints.md`) presents the close-list. The user may drop any issue whose work isn't actually complete; dropped issues get no `Closes` line and stay open (the orchestrator may post a brief comment on a dropped issue noting the run addressed it only partially, linking the PR).
- The existing `merge` phase triggers GitHub's native auto-close of the listed issues on merge to the default branch. If the run stops before merge, nothing is closed.
- If `source_issues` is empty (the run fell back to a description), no `Closes` lines are added — pr_creation behaves exactly as today.

## 4. State schema

`references/state-schema.md` gains one field:

- `source_issues`: list of `{ "number": int, "title": string, "url": string }` for the issues a run is built from. Present only for issue-driven `feature_addition` runs; **unset (key omitted)** otherwise, per the schema's existing convention.
- Set once, at Step 0, when issues are selected. Read at pr_creation to build the `Closes #N` list. Carried through resume unchanged — a resumed run still closes its issues even in a later session.

## 5. Checkpoint presentation

- Step 0 checkpoint: when issues seeded the run, the summary lists the selected issue numbers/titles and notes any that were named-but-skipped (nonexistent/already-closed).
- pr_creation checkpoint: additionally presents the `Closes #N` list with the drop-any control described in §3. Existing PR-summary content is unchanged.

## 6. Error handling & gating (all soft-fail)

- No `gh` / not authed / no GitHub remote / no open issues → issue path unavailable, normal description flow, no error.
- `gh issue view` fails on a selected issue → surface the error; offer retry or skip that issue; never abort the run.
- A named issue number that doesn't exist or is already closed → warn and skip it, note it in the Step 0 summary.
- pr_creation with empty `source_issues` → no `Closes` lines; identical to today.

## 7. Affected documents

- `skills/ios-genesis/references/issue-driven-runs.md` — **new**; gating detection, `gh` commands, selection UX, interview seeding, closing rules.
- `skills/ios-genesis/references/orchestration-flow.md` — Step 0 gains: detect remote+`gh` → offer/fetch issues → seed interview → persist `source_issues`.
- `skills/ios-genesis/references/state-schema.md` — `source_issues` field + init/resume notes.
- `skills/ios-genesis/references/checkpoints.md` — Step 0 issue summary; pr_creation `Closes #N` review.
- `skills/ios-genesis/references/pr-review-flow.md` — pr_creation PR body includes `Closes #N` from `source_issues`.
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
- Scope check: the feature touches only orchestrator references/docs + `plugin.json`; no new agent files required (the orchestrator drives `gh`, consistent with the existing repo/PR flow).
