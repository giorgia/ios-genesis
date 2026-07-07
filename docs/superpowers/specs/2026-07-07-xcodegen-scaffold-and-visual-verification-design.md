# xcodegen Scaffold & Visual Verification — Design

**Date:** 2026-07-07
**Status:** Approved by user (brainstorming session)

## Context

The end-to-end dry run (counter app, June 2026) exposed two structural gaps:

1. **SPM-first scaffolding**: `new_app` produced a Swift package with no app bundle — not installable on a simulator, no XCUITest possible, and App Store readiness required a follow-up scaffolding run. That follow-up run produced a working xcodegen `project.yml` which this design adopts as the template.
2. **No visual verification**: every pipeline loop terminates at "compiles and unit tests pass." A visual regression (a `.buttonBorderShape(.circle)` collapsing around a short SF Symbol glyph, introduced by a round-2 code-review polish item) shipped because nothing in the pipeline ever rendered the app.

This design makes an installable Xcode app the `new_app` default (Feature 1) and adds a simulator-in-the-loop visual verification phase (Feature 2). Feature 1 is a prerequisite for Feature 2.

## Goals

- `new_app` runs produce a simulator-installable `.xcodeproj` app by default.
- Every run that touches screens gets its rendered UI structurally compared against the design reference, with a bounded fix loop.
- Graceful degradation everywhere: missing tooling or un-installable existing apps produce actionable risks, not failed runs.

## Non-goals (v1)

- Simulator interaction (tapping, navigation). Verification covers the launch screen only; deeper screens are reported as unverified. XcodeBuildMCP integration is the documented follow-up.
- Pixel-perfect comparison. Verification is structural/semantic judgment, not screenshot diffing.
- Swift Testing migration, model routing, eval harness (separate roadmap items).

---

## Feature 1: xcodegen app-target scaffold

### 1.1 Prerequisite check (orchestrator)

Before dispatching `ios-developer` with `dispatch_type: implement` for `mode: new_app`, the orchestrator runs `which xcodegen`. If not found, it tells the user:

> "The `new_app` scaffold requires xcodegen. Install it with `brew install xcodegen`, then re-run `/ios-genesis <path>` to resume from this point."

and stops. `state.json` is unchanged (`phase: developer`, `phase_status: in_progress` not yet written — the check runs before the dispatch and before any state update for the phase), so resuming re-enters at the developer phase. This mirrors the existing `gh auth status` prerequisite check in `pr-review-flow.md`.

`feature_addition` does not require xcodegen (existing projects keep their own build setup) — the check runs only for `new_app` `implement`.

Documented in: `orchestration-flow.md` (new-app step 3) and the developer agent's `implement` section.

### 1.2 Developer scaffold changes (`agents/ios-developer.md`, `implement`, `new_app`)

Replace the current SPM-first guidance ("scaffold … using Swift Package Manager … or a minimal `.xcodeproj` if that's required") with:

- Scaffold an xcodegen-based Xcode project at `target_project_path`:
  - `project.yml` defining **only the app target** and its scheme. Template (proven by the counter app's follow-up run):
    - `type: application`, `platform: iOS`, deployment target = latest stable iOS major (currently 17.0+; use judgment per `architecture_summary`)
    - explicit `Info.plist` (`GENERATE_INFOPLIST_FILE: NO`) so the release manager has a real file to audit
    - `PrivacyInfo.xcprivacy` (empty-but-valid privacy manifest)
    - `Assets.xcassets` with an `AppIcon` placeholder set
    - `PRODUCT_BUNDLE_IDENTIFIER: com.example.<AppName>`, `MARKETING_VERSION: 1.0.0`, `CURRENT_PROJECT_VERSION: 1`, `CODE_SIGN_STYLE: Automatic`, empty `DEVELOPMENT_TEAM`
    - a scheme with build/run/test/profile/analyze/archive configs
  - `<AppName>/` source directory: `@main` app entry, views/models per `design_summary`/`architecture_summary`
  - Run `xcodegen generate` after writing/updating `project.yml`. Both `project.yml` and the generated `.xcodeproj` are kept (committed later at `pr_creation`) so the repo is usable without xcodegen installed.
- Build with `xcodebuild build -scheme <AppName> -destination 'platform=iOS Simulator,name=<an available iPhone>'` (query `xcrun simctl list devices available` to pick one). Same retry policy as today: 3 attempts, then stop and report.
- The `com.example.*` bundle id is noted in the developer's report `risks` so it flows into the release checklist.

**Do NOT define test targets in `project.yml`** — a target whose source directory doesn't exist yet breaks `xcodegen generate`, and writing placeholder tests would violate the developer's role boundary (test code belongs to the Test Engineer).

`feature_addition` behavior is unchanged (follow the existing project's structure and build system).

SwiftUI Pro review, report format, and all other `implement` behavior are unchanged.

### 1.3 Test engineer changes (`agents/ios-test-engineer.md`)

For xcodegen-based projects (a `project.yml` exists):

- Add a unit-test target (and a UI-test target where appropriate — at minimum a launch smoke test for new apps) to `project.yml`, following the template conventions (e.g. `bundle.unit-test` with `TEST_HOST` pointing at the app, `bundle.ui-testing` depending on the app target). Register the new target(s) in the scheme's `test` section.
- Re-run `xcodegen generate` after editing `project.yml`.
- Run `xcodebuild test -scheme <AppName> -destination 'platform=iOS Simulator,name=<an available iPhone>'`. Same 3-attempt retry policy and app-bug escalation rule as today.

Pure-SPM projects (some `feature_addition` targets) keep the existing `swift test` path.

### 1.4 Role-boundaries updates (`references/role-boundaries.md`)

- `developer` expected paths: add `project.yml`, `*.xcodeproj`, `Info.plist`, `PrivacyInfo.xcprivacy`, asset catalogs.
- `test_engineer` expected paths: extend the test-target-registration carve-out to `project.yml` edits and the regenerated `.xcodeproj` (new app only).

---

## Feature 2: visual verification

### 2.1 New agent: `agents/ios-visual-verifier.md`

- **Frontmatter**: `tools: Read, Bash, WebFetch, mcp__claude_ai_Figma__get_screenshot`, `model: sonnet`.
- **Role**: verifies that the implemented app's rendered UI structurally matches the design. Read-only toward source code: it builds/installs/launches/screenshots, but never edits project files, never commits, and never fixes anything — findings route through the Developer.

**Inputs** (dispatch prompt):
- `mode`, `target_project_path`, `design_mode`
- `design_summary`: contents of `docs/design.md`
- `design_reference`: the mode-specific visual reference — the Figma file link (from `docs/design.md`'s "Figma File" section) for `figma`; the `design_sources` list for `bring_your_own`; `"none"` for `text`/`claude_design` (compare against `design_summary` itself)
- `app_scheme`: the scheme name for `new_app` (the orchestrator knows it — the app name); `"discover"` for `feature_addition`
- `verification_round`: 1 or 2
- For round 2: `previous_findings` (its own round-1 findings, verbatim)

**Procedure**:
1. Resolve the scheme: use `app_scheme`, or for `"discover"` run `xcodebuild -list` in `target_project_path` and pick the app scheme (use judgment; if ambiguous, pick the scheme matching the project name).
2. Pick the newest available iPhone from `xcrun simctl list devices available`; boot it if not booted (`xcrun simctl boot`; already-booted is fine).
3. Build for that simulator (`xcodebuild build -scheme … -destination …`), locate the `.app` via `xcodebuild -showBuildSettings` (`BUILT_PRODUCTS_DIR`/`FULL_PRODUCT_NAME`), then `xcrun simctl install booted <app>` and `xcrun simctl launch booted <bundle-id>` (bundle id via `-showBuildSettings` `PRODUCT_BUNDLE_IDENTIFIER`).
4. Wait ~3 seconds for the UI to settle, then `xcrun simctl io booted screenshot .ios-orchestrator/screenshots/round-<N>-launch.png`. (`.ios-orchestrator/` is already gitignored by the scaffold.)
5. Read the screenshot (multimodal). Obtain the reference: `figma` → `get_screenshot` on the Figma file/frame; `bring_your_own` → `Read` local images / `WebFetch` URLs; `text`/`claude_design` → the screen's described hierarchy in `design_summary`.
6. Compare **structurally**: every component in the design present, roughly the right shape/size/position, no clipped/collapsed/overlapping elements, no crash or blank screen. Do NOT flag minor spacing, font rendering, or color-space differences. Calibration example (from the dry run): a circular button whose border shape collapsed around a short glyph into a small pill — wrong shape and size, fails against any reference form.
7. Round 2: additionally check each item in `previous_findings` — resolved or not.

**Skip semantics**:
- `feature_addition`: if the app can't be built for / installed on a simulator (signing requirements, workspace quirks, no app scheme found), report `status: skipped` with the reason. Not a failure.
- `new_app`: install/launch failure of our own scaffold is a defect — report it under `status: issues_found` so it routes to the Developer fix loop. A crash on launch is likewise `issues_found`.
- No available iPhone simulators at all (either mode): `status: skipped` with the reason.

**Report format**:

```
## Visual Verifier Report
- verification_round: <1|2>
- status: <pass|issues_found|skipped>
- screenshots: <paths under .ios-orchestrator/screenshots/, or "none">
- findings: <numbered list: screen, what's wrong, which reference item it violates — or "none">
- unverified: <screens in design_summary not reachable from the launch screen without interaction, or "none">
- risks: <bullet list, or "none">
```

**Role boundaries**: builds and simulator operations only; no source/project file edits; no commits; no design judgment beyond the comparison (a finding cites the design reference it violates — taste-only objections go under `risks`, not `findings`).

### 2.2 New phase: `visual_verification` (orchestration)

Inserted between `developer` and `test_engineer` in **both** modes, and run **only if `screens_affected: true`** (same condition as `ui_designer`). Placement before `test_engineer` means tests are written against final, visually-verified code.

Loop (mirrors the `code_review` loop, capped at 2 rounds):

1. Set `verification_round: 1`. Dispatch `ios-visual-verifier`.
2. `status: pass` → run the standard checkpoint, proceed to `test_engineer`.
3. `status: skipped` → append an `open_risks` entry with the skip reason, run the standard checkpoint, proceed. (Do not loop.)
4. `status: issues_found`:
   a. Dispatch `ios-developer` with new `dispatch_type: address_visual` (see 2.3).
   b. If `verification_round == 1`: increment to 2, re-dispatch the verifier with `previous_findings`, go to step 2.
   c. If `verification_round == 2` and findings remain: stop looping. Append the unresolved findings as `open_risks` entries and surface them at the checkpoint — the user decides (Continue / Make changes first / Stop).
5. The checkpoint runs once, after the loop concludes (like `code_review`). `phase_status: "complete"` either way; `verification_round` is persisted as set by the loop.

### 2.3 Developer `dispatch_type: address_visual` (`agents/ios-developer.md`)

Additional input fields:
- `verifier_findings`: the Visual Verifier's findings, verbatim
- `screenshot_paths`: so the developer can look at the actual rendered result
- `work_summary`: from `phases_completed` (no memory between dispatches)

Steps: read the screenshots and findings, fix each finding in the code, rebuild (3-attempt policy), run the SwiftUI Pro review, do NOT commit (matches `implement`; commits happen at `pr_creation`). Report as usual.

### 2.4 State & reference-doc changes

- `state-schema.md`: `phase` enum gains `visual_verification`; new field `verification_round` (0 before the first verifier dispatch, then 1–2; monotonic within the phase, analogous to `review_round`); `phases_completed` artifact for the phase is `.ios-orchestrator/screenshots/` (or `"none"` if skipped).
- `checkpoints.md`: persist `verification_round` as set by the loop (same rule as `review_round`); the checkpoint summary must include the verification verdict and reference the screenshot(s).
- `role-boundaries.md`: new `ios-visual-verifier` row (in scope: simulator build/install/launch/screenshot, comparison; out of scope: any file edits, commits). Scope check: `git status --porcelain` expected clean (screenshots live under the exempt `.ios-orchestrator/`); for the `address_visual` sub-dispatch, expected paths = same as `developer`.
- `orchestration-flow.md`: insert the phase in both mode sequences (renumber), with the `screens_affected` condition and a pointer to the loop procedure. Add the xcodegen prerequisite check to the new-app developer step.
- `SKILL.md`: add the verifier to the team description; no new reference doc (the loop lives in `orchestration-flow.md` — it's short enough).
- `.claude-plugin/plugin.json` + `marketplace.json` description updates; version → `0.2.0`.
- `README.md`: pipeline diagram gains the verification phase and its fix-loop back-edge; agent table gains the verifier row; "Loop engineering" gains the visual loop; limitations section drops the two items this design fixes and keeps interaction/deep-screen verification as the stated edge.

## Error handling summary

| Condition | Behavior |
|---|---|
| xcodegen missing (`new_app`) | Orchestrator stops pre-dispatch with install instructions; run resumes at developer |
| xcodegen generate fails | Counts against the developer's 3 build attempts |
| No available iPhone simulator | Verifier reports `skipped`; open_risk; run continues |
| `feature_addition` app won't install | Verifier reports `skipped` + reason; open_risk; run continues |
| `new_app` scaffold won't install/launch or crashes | `issues_found` → developer fix loop |
| Findings persist after round 2 | Loop stops; findings become open_risks; user decides at checkpoint |
| Figma reference unreadable (`get_screenshot` fails) | Fall back to `design_summary` text comparison; note under `risks` |

## Validation

1. **New-app dry run** on a fresh scratch directory: confirm installable app, verifier screenshot, and loop behavior (ideally observe at least one real finding→fix cycle).
2. **feature_addition dry run** against the existing counter-app repo: exercises scheme discovery and (if install fails) graceful skip.
3. Confirm `resume` still works with the new phase in the sequence.
