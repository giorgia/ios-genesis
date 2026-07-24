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
