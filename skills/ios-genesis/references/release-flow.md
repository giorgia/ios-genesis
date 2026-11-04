# Release Flow

The **release run** prepares a new App Store version end to end: version bump, Release-only checks, upgrade safety, the full test suite, store copy, screenshots, App Store Connect sync and the build upload. It stops **before submission**: submitting for review is always the user's act in App Store Connect, and nothing in this plugin can do it.

The worked example is Cadenza 3.0.0 (giorgia/Cadenza#123). Most of that release was orchestrated by hand; each lesson from it is now a step or a check below, marked *(3.0.0)* where it came from.

## Starting a release run

`/ios-genesis <target-project-path> release [<version>]` — the description's first word is `release`. A description that reads like a release request without the keyword ("ship 3.0 to the App Store", "prepare the store submission") gets one `AskUserQuestion`: start a release run, or treat it as a feature. The project must already exist and build; a release run never scaffolds.

A release run sets `mode: "release"` and `lane: "release"` in `state.json`, skips the architect classification and the Step 0 brainstorming interview (the `release_intake` questions replace them), and runs the phases below in order, each followed by the standard checkpoint (`checkpoints.md`) unless the phase is a **gate**, which has its own stricter question.

The `release_manager` phase that ends a `new_app` run (and is opt-in after `feature_addition`) still writes only the readiness checklist. Its checkpoint offers to start a release run next.

## Gates: what needs the user's explicit OK

Ordinary checkpoints offer Continue / Make changes first / Stop. A **gate** is different: it is an outward or hard-to-reverse act, and the orchestrator asks for that one act by name, with what it will do and where, and acts only on an explicit yes given in this conversation. A Continue at an earlier checkpoint is not a yes for a gate. An approval covers one act once: a re-run after a failure, or the same act for another locale or another build, asks again.

| Gate | Act | Who runs it after the yes |
|---|---|---|
| G1 `asc_write` | `asc_sync.py sync --version <v> --apply`: creates the version if missing, writes name, subtitle, promo, keywords, description, What's New, required URLs and review notes, and replaces screenshot sets. The question shows the `plan` output it will apply. `--text-only` and the screenshot upload may be approved separately. | orchestrator |
| G2 `account_signing` | Any command that may create or change certificates, profiles or App ID capabilities in the user's developer account: `-allowProvisioningUpdates`, or letting Xcode fix signing | orchestrator |
| G3 `build_upload` | `xcodebuild -exportArchive` with `destination: upload`, or handing the user the Organizer steps | orchestrator, or the user (path C) |
| G4 `attach_build` | `asc_sync.py attach-build --version <v> --build <n> --apply` | orchestrator |
| G5 `merge` | Squash-merging the release PR into the default branch | orchestrator (`pr-review-flow.md`) |
| G6 `tag` | `git tag v<version> <archived commit>` and `git push origin v<version>`, only once the user says the version was submitted or approved *(3.0.0: tags mirror the App Store; a tag exists only for a submitted version)* | orchestrator |
| — `submit` | **Never.** No script, agent or orchestrator step submits for review, releases a version, starts a Product Page Optimization test, or calls a review-submission endpoint, even if asked mid-run. The orchestrator tells the user it's theirs to do in App Store Connect. | the user |

Everything else in the run is local and reversible (branches, commits on the release branch, builds, simulator installs, dry runs, read-only API calls) and runs without a gate.

Approvals are recorded in `state.json` as `release.gates.<gate>: {"approved_at": <ISO-8601>, "result": <short outcome>}` so a resumed run never mistakes an old approval for a new one: a resume asks again for any gate whose act hasn't completed.

## Phases

| # | Phase | Runs it | Writes | Gate |
|---|---|---|---|---|
| 1 | `release_intake` | orchestrator | `state.json` `release.*` | — |
| 2 | `version_bump` | `ios-developer` (`version_bump`) | project version settings | — |
| 3 | `release_audit` | `ios-release-manager` (`audit`) | `docs/release-checklist.md` §Release build | — |
| 4 | `upgrade_check` | `ios-test-engineer` (`upgrade_check`) | checklist §Upgrade (via report) | — |
| 5 | `release_tests` | `ios-test-engineer` (`release_suite`) | checklist §Tests (via report) | — |
| 6 | `store_assets` | `ios-release-manager` (`store_assets`) | `docs/appstore-metadata.md`, `docs/app-review-notes.md`, `docs/aso-plan.md` | — |
| 7 | `screenshots` | `ios-release-manager` (`screenshots`) | `docs/appstore-screenshots/**` | — |
| 8 | `release_pr` | `ios-developer` (`create_pr`) + `ios-code-reviewer` | the PR | G5 at the end |
| 9 | `asc_sync` | orchestrator | App Store Connect | G1 |
| 10 | `build_upload` | orchestrator | App Store Connect | G2, G3, G4 |
| 11 | `release_handoff` | `ios-release-manager` (`checklist`), then orchestrator | `docs/release-checklist.md` | G6 later |

Code fixes found by phases 3–5 (a missing privacy reason, a data-loss bug, a regression) go to `ios-developer` with `dispatch_type: address_release_finding` on the release branch, then the finding phase re-runs. Never fold a fix into an audit agent.

### 1. `release_intake`

1. Capability preflight (`capability-preflight.md`) as for every run.
2. **Ask up front** *(3.0.0)*, one `AskUserQuestion` per decision, recommendation first:
   - **Version.** Read the live version from the iTunes lookup (`https://itunes.apple.com/lookup?id=<app_id>`) and the repo's current `MARKETING_VERSION`. Propose patch / minor / major with a reason (several new user-facing features, a minimum-OS change or a data migration argue for a major). Build number resets to 1 on a new marketing version; it increments only for a resubmission of the same version.
   - **Positioning.** One line: what this version leads with on the product page (3.0.0: "import first, hands-free counting second"). It drives the store copy, screenshot order and keywords.
   - **Blocking issues.** Which open issues or known bugs must be fixed before this ships. Fixing them is feature work: run it through the quick lane or the full pipeline on the release branch *before* `release_audit`, not inside the release phases.
   - **Locales**, and whether the run makes screenshots, Duo sets, creatives, an ASO pass.
3. **Branch.** `git fetch origin`, then create `release/<version>` from the latest `origin/<default>` (never from a stale local default, never from a feature branch). If it exists, ask: reuse it or suffix `-2`. Persist as the working branch.
4. **Previous release.** Record the previous App Store version and its git tag (`v<prev>`). If the tag is missing, ask which commit shipped; the upgrade check needs it.
5. **Release preflight** (`release-preflight.md`): credentials, app access, App ID capabilities, signing paths. Print its block.
6. Copy the per-project config the scripts need if missing: `scripts/asc/asc-config.json` from `scripts/asc-config.example.json` (no secrets), filled from `project.yml`/the entitlements files and the user's app id.

Checkpoint: the intake answers, the branch and base SHA, the preflight block, and the phase plan with its gates.

### 2. `version_bump`

`ios-developer` with `dispatch_type: version_bump`, `version`, `build`. It sets `MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` (or the `Info.plist` keys if the project doesn't use build settings) **on every target that ships in the bundle: the app and every extension, App Clip and watch app, together** *(3.0.0: app and share extension)*. Apple rejects an upload whose extension version doesn't match the app's. Then `xcodegen generate` if the project uses it, a build, and a commit `release: <version> (<build>)`.

### 3. `release_audit`

`ios-release-manager` with `dispatch_type: audit`. These are the checks a Debug simulator build never exercises *(3.0.0)*:

1. `xcodebuild archive -scheme <scheme> -configuration Release -destination 'generic/platform=iOS' -archivePath build/release/<App>-<version>-<build>.xcarchive` (no `-allowProvisioningUpdates`: archiving signs for development and changes nothing in the account). Record the Xcode and SDK versions and the warning count.
2. `release_audit.py archive <xcarchive> --expect-version <v> --expect-build <b> [--debug-marker …]`: every bundle's version/build, signing, `codesign --verify --deep --strict`, entitlements, a `PrivacyInfo.xcprivacy` **in each bundle**, and `strings` on each executable for DEBUG-only routes and fixtures (`ios-genesis-screen`, `DebugRouter`, `DebugRegistry`, plus the project's fixture and seed type names).
3. `release_audit.py reasons --target <name> <manifest> <dirs…>` for **every target, extensions included**, listing every source folder the target compiles (read `project.yml` `sources`: a shared folder compiled into an extension counts) *(3.0.0: the share extension needed its own manifest for `UserDefaults` used by shared inbox code; the app needed `FileTimestamp` for a new `modificationDate` read)*.
4. `release_audit.py network <dirs…>`: list network code, to check against the privacy label, the privacy policy and any "works offline / no data collected" claim.
5. `Info.plist` and entitlements diff against the previous release tag: new capabilities (each needs the App ID capability, see the preflight) and new usage descriptions.

Every ✗ is a finding: code fixes go to the developer (above); the rest become checklist action items. Checkpoint: the audit table.

### 4. `upgrade_check`

`ios-test-engineer` with `dispatch_type: upgrade_check`, `previous_ref` (the previous release's tag) and `scheme`. An update must keep the user's data *(3.0.0: adding an App Group entitlement made SwiftData's default `ModelConfiguration(groupContainer: .automatic)` open a new, empty store in the group container; updating 2.0.0 users would have lost their whole history. Fixed by moving the store to the App Group with a one-time copy of the old store, WAL and SHM first)*.

1. `git worktree add <tmp> <previous_ref>`, build it for the simulator, install it on a fresh simulator (`simctl erase` first).
2. Put **real data** in it: drive the app (XcodeBuildMCP, or the DEBUG router's seed routes if the old build has them) to create records of every persisted type. Record what was created.
3. `simctl install` the new build **over** it: no uninstall, no erase. Launch.
4. Check every record survived and is usable (read through the UI or the app's container: `simctl get_app_container <udid> <bundle> data` and, for App Groups, `groups`). Relaunch twice.
5. Run any migration tests the project has.

A loss is a **blocker** for the release (`open_risks`, impact first) and goes to the developer. The real-device version of this check — the App Store build on a phone with real data, then the TestFlight build over it — is a user step the checklist carries; the simulator check doesn't replace it. Clean up the worktree.

### 5. `release_tests`

`ios-test-engineer` with `dispatch_type: release_suite`:

1. The **full** suite on the release branch, unit and UI.
2. For every failure, the same tests on **clean `origin/<default>`** in a temporary worktree. Failing on both → *pre-existing* (an `open_risks` follow-up, not a release blocker unless the user says so). Failing only on the release branch → *regression* → developer.
3. Flaky tests: re-run a failing test alone up to twice; a test that passes alone but fails in the suite is reported as flaky with both results, never silently retried to green.
4. **Simulator limits.** Parallel test clones can exhaust the per-user process limit or the simulator service ("Too many open files", clones failing to boot, `launchd` spawn errors). Run with `-parallel-testing-worker-count 2` (or `-parallel-testing-enabled NO` for UI tests), `xcrun simctl shutdown all` between the two runs, and report the destination used.

Checkpoint: totals, the pre-existing vs regression table, and flaky tests.

### 6. `store_assets`

`ios-release-manager` with `dispatch_type: store_assets`, `positioning`, `locales`, `previous_version`. It writes `docs/appstore-metadata.md` and `docs/app-review-notes.md` (templates in `templates/`) and, when the ASO pass was chosen, `docs/aso-plan.md`.

- **Limits**: name 30, subtitle 30, promo 170, keywords 100, description 4,000, What's New 4,000, review notes 4,000. `asc_sync.py check` enforces them.
- **No platform trademarks** in name, subtitle or keywords (Guideline 5.2.5; Cadenza 1.0.0 was rejected for "AirPods" in the subtitle). No other platform's name or logo anywhere in the listing or screenshots (`banned_terms`).
- **Claims checked against the code.** Every What's New and description claim must be backed by code on the release branch or a recorded check. Anything unverified ("works on iPhone Duo", "VoiceOver is much better") becomes a user decision: verify, soften or cut *(3.0.0)*. What's New lists only what's new since the last shipped version.
- **Review notes** under 4,000 characters, with a devices-tested line that matches what was actually run.
- **Privacy policy accuracy.** Fetch the live policy URL and compare it with what the code does (data read from Health, on-device ML, extensions, networking, shared links). A mismatch is a submission blocker owned by the user *(3.0.0: the policy said the app read no health data)*. Also re-derive the App Privacy (nutrition label) answers and list them for the user to confirm.
- **ASO** (optional): `aso_rank.py` for the current and candidate terms, US storefront, top 200; competition = median rating count of the top 10. Recommend name/subtitle/keyword changes with the reason per field; keep a term the name already ranks for. Apple doesn't publish volume: say so, and point to Apple Search Ads keyword popularity.
- **Product Page Optimization readout.** Don't propose a PPO test at low traffic: a two-variant test needs roughly 17–50 unique impressions a day to reach 90% confidence within 90 days *(Cadenza: four variants at ~6.7 a day ended with no winner)*. Instead, record a 28-day baseline from App Analytics **before the build is uploaded** (it can't be reconstructed later) and plan day-14 and day-28 checkpoints with the same rank query.
- Finish with `asc_sync.py check`, then `asc_sync.py plan --version <v> --text-only` (read-only; needs credentials) to show what G1 would change.

Checkpoint: the copy per locale with character counts, the check output, the `plan` diff, the claims and privacy findings. The user approves the **copy** here; that approval is not G1.

### 7. `screenshots`

`ios-release-manager` with `dispatch_type: screenshots`. Skipped if the user chose to keep the current sets (a new version keeps the previous version's screenshots).

1. Copy the templates into the project if absent: `scripts/screenshots/capture.sh` → `docs/appstore-screenshots/capture.sh`, `compose.py` and a `shots.json` started from `shots.example.json`. The **look is project-specific**: fonts, colors and layout come from the app's design system and the user's approval, not from the template's defaults.
2. **Shot list** from the positioning: what each shot shows, its caption per locale. Shots 1–3 appear in search results, so they carry the story. Present the list at the checkpoint before capturing.
3. **Capture** through the DEBUG router (`-ios-genesis-screen <Name>`) on the simulator whose native size is the largest slot (iPhone Pro Max class, 1320×2868), per locale (`--locale`), with the status bar overridden to 9:41 and permissions pre-granted. Duo: `--display primary` for the outer display, `primary-1` for the open one; folding is done by hand in Simulator.app, and display ids can swap after folding, so check each raw's pixel size.
4. **Device-only shots** (live sensor readings, real video) are user captures: list exactly which, the path to drop each at, and the minimum resolution. Never fake a hardware-only state in the simulator.
5. **Compose** with `compose.py`: per-locale sets in every slot, Duo outer/inner sets, header (3840×1646) and search (3840×2560) creatives. The status bar is cropped with a top margin. Third-party creator handles, faces and anyone else's content are blurred (`redact`), because advertising with them needs permission (Guideline 5.2).
6. `compose.py --verify`, then look at every image. Screenshots must show the real shipping UI (Guideline 2.3.3): a raw from an older version, or a screen whose controls changed, is a blocker *(3.0.0: shot 2 still showed 2.0.0's controls)*.

Checkpoint: the images (send the composed files), the device captures still owed, and anything that names or shows another platform.

### 8. `release_pr`

`pr-review-flow.md` with `branch_name: release/<version>` against the default branch: `create_pr`, the review loop, then **G5** before merging. A release PR usually stays open until the build is accepted for upload; ask whether to merge now or after `build_upload`. The PR body summarizes fixes, version, store changes, checks and the user's remaining steps *(shape: giorgia/Cadenza#123)*.

### 9. `asc_sync` (G1)

1. `asc_sync.py plan --version <v>` (read-only) and show the diff.
2. **G1**: ask for the write by name, showing the plan. On yes, `asc_sync.py sync --version <v> --apply --yes` (the typed confirmation is replaced by the user's explicit yes in chat, which the orchestrator quotes in `release.gates.asc_write`).
3. `asc_sync.py plan --version <v>` again: every field must read *unchanged*. Anything else is reported, not retried blindly.
4. Name and subtitle are editable only once the new version exists; if the first apply created the version, a second plan shows them pending. Ask before a second apply.
5. Duo screenshot sets have no API display type: list them for the user to upload in App Store Connect's iPhone Duo tab. A missing review detail (contact info) is also a user step; re-run after.

### 10. `build_upload` (G2, G3, G4)

1. Re-run the release preflight. A ✗ on capabilities stops here with the fix.
2. **Local export check** (no gate, nothing leaves the machine): `xcodebuild -exportArchive -archivePath <xcarchive> -exportPath build/release/export -exportOptionsPlist <plist with destination export>` **without** `-allowProvisioningUpdates`. Success proves path A. A profile or certificate error means path A isn't ready.
3. If path A failed and the user wants path B: **G2** (it may create distribution certificates or profiles in their account), then the same export with `-allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"`. "Cloud signing permission error" means the key isn't Admin: offer path C, don't retry.
4. **G3**: upload by name ("upload <App> <version> (<build>) to App Store Connect"). On yes, the same export with `destination: upload`. Or, for path C, give the Organizer steps and wait for the user to say it's done.
5. `asc_sync.py builds --version <v>` until the build is `VALID` (processing takes minutes to an hour; check at sensible intervals, don't spin). An `INVALID` build: report Apple's email/validation message, don't re-upload the same build number.
6. **G4**: attach the build to the version.

ExportOptions plist (the `teamID` comes from the project's `DEVELOPMENT_TEAM`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>export</string>  <!-- `upload` only after G3 -->
  <key>teamID</key><string>TEAMID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>uploadSymbols</key><true/>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
```

`manageAppVersionAndBuildNumber: false` keeps the version the run set and audited.

**Organizer fallback (path C):** Xcode → Window → Organizer → Archives → select `<App> <version> (<build>)` → Distribute App → App Store Connect → Upload → automatic signing → Upload. The signed-in Apple account must be Admin/Account Holder or have "Access to Cloud Managed Distribution Certificate"; every App ID needs every capability first.

### 11. `release_handoff`

`ios-release-manager` with `dispatch_type: checklist` finalizes `docs/release-checklist.md` (shape below), committed on the release branch (or the default branch if the PR is merged). Then the orchestrator tells the user, in one message, what's done and what is theirs:

- **Submit for review in App Store Connect** (and choose manual or automatic release).
- Upload Duo sets by hand; attach the review screen recording if the notes promise one; confirm App Privacy answers; update the privacy policy if flagged.
- Device checks the simulator couldn't do, including the App Store → TestFlight update with real data.
- Capture the 28-day ASO baseline if not done.
- Tell the orchestrator when it's submitted or approved, to run **G6** (tag the archived commit, push the tag) and record the date.

The run ends with `phase: "release_handoff"`, `phase_status: "complete"`. Resuming it later (after submission) offers G6 and the day-14/day-28 ASO checkpoints.

## `docs/release-checklist.md` shape

Kept current through the run, one numbered section per area *(3.0.0's checklist)*: Status (version, build, branch, base SHA, what's done in App Store Connect, "No build uploaded / Not submitted" until true) · Release history table · Why this version · Version and device family · Info.plist, privacy manifests, entitlements, App Privacy, privacy policy · Release build and DEBUG seams · Tests (pre-existing vs regressions) · Upgrade / data migration · App Review risks · Requirements (Xcode, SDK, slots) · Store metadata and screenshots · Known limitations carried forward · Pre-submission action list (done / user steps) · Post-submission steps (tag, ASO checkpoints, ratings) · Readiness summary.

## State

`state.json` for a release run adds a `release` object (see `state-schema.md`): `version`, `build`, `previous_version`, `previous_ref`, `positioning`, `blocking_issues`, `locales`, `base_sha`, `archive_path`, `preflight`, `signing_path`, and `gates`. It never holds credentials.
