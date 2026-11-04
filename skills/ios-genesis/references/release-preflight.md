# Release Preflight

The single authority for **deciding, before anything is archived, whether this release can be signed and uploaded the way the run plans to**. It runs once, in the release run's `release_intake` phase (`release-flow.md`), after the capability preflight (`capability-preflight.md`) and the intake questions. It reruns on resume, and once more right before the `build_upload` gate, because App Store Connect keys and App ID capabilities change outside the run.

## Why it exists

Cadenza 3.0.0 got all the way to a signed-off release archive and then failed at upload. `xcodebuild -exportArchive` (method `app-store-connect`, destination `upload`, `-allowProvisioningUpdates` with the `-authenticationKey*` flags) stopped with **"Cloud signing permission error"** and **no distribution profiles** for the App Groups and Associated Domains capabilities that 3.0.0 had just added. Two independent causes:

1. **The key's role.** Cloud-managed distribution certificates are reachable from an API key only with the **Admin** role. The key was App Manager: enough to write the listing, not enough to sign for distribution.
2. **App ID capabilities.** Every App ID (app *and* each extension) needs every capability its entitlements use, or no App Store profile can be issued for it. Automatic signing had added them for *development*; that says nothing about distribution.

Both were knowable before archiving. Finding them at upload wasted the archive and left the user with an unplanned Organizer session. This preflight finds them up front.

## What it checks

| Check | How | Result states |
|---|---|---|
| `credentials` | `ASC_KEY_PATH`, `ASC_KEY_ID`, `ASC_ISSUER_ID` set; the key file isn't group/world readable | ✔ set / ✗ missing (listing sync and API upload unavailable; everything else still runs) |
| `app_access` | `asc_sync.py preflight`: `GET /v1/apps/<app_id>` and the version's state | ✔ / ✗ wrong app id or no access |
| `capabilities` | `asc_sync.py preflight`: for each `targets` entry in `scripts/asc/asc-config.json`, the entitlements file's keys mapped to capability types, compared with the App ID's `bundleIdCapabilities` | ✔ all present / ✗ `<bundle id>` lacks `<CAP>` (a blocker for every signing path) / `!` key can't read provisioning |
| `profiles` | `asc_sync.py preflight`: active `IOS_APP_STORE` profiles per bundle id | listed, feeds path A |
| `local_identity` | `security find-identity -v -p codesigning` contains `Apple Distribution` | feeds path A |
| `toolchain` | `xcodebuild -version`, the SDK; Pillow (`python3 -c "import PIL"`) if screenshots are planned | reported; a missing Pillow only affects the screenshots phase |

`asc_sync.py preflight` is read-only: it never creates an App ID, a capability, a certificate or a profile. Fixing a missing capability is the user's act (developer.apple.com → Identifiers), or Xcode's when the user lets it run with an Admin account.

## The signing paths

The preflight reports which of three paths can work. The run picks one at the `build_upload` gate with the user.

- **A. Local signing.** An Apple Distribution identity in this keychain and an active App Store profile for every bundle id. `-exportArchive` with `signingStyle: manual` (or automatic without `-allowProvisioningUpdates`) works with no account access at all.
- **B. Cloud signing with the API key.** `-allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"`. Needs an **Admin** key. The API doesn't expose a key's role, so the preflight can only say *unknown* here. A key that gets 401/403 on provisioning endpoints certainly can't (✗).
- **C. Xcode Organizer.** Window → Organizer → the archive → Distribute App → App Store Connect → Upload. Uses the Apple account signed in to Xcode, which must be Admin/Account Holder or have "Access to Cloud Managed Distribution Certificate". Always available as the fallback.

A ✗ on `capabilities` blocks all three paths. Path A or B still needs the **local export check** after archiving (`release-flow.md`, `build_upload`): exporting with destination `export` signs exactly as the upload would, without sending anything.

## Output: report it at intake, not at upload

Print the block right after the capability block, before any code changes. Illustrative, shaped on the 3.0.0 failure:

```
Release preflight — Cadenza 3.0.0
  ✔ credentials     ASC_KEY_* set, key file 0600
  ✔ app access      Cadenza: Workout Rep Counter (com.giorgia.Cadenza), 3.0.0 not created yet
  ✗ capabilities    com.giorgia.Cadenza lacks APP_GROUPS, ASSOCIATED_DOMAINS
                    com.giorgia.Cadenza.ShareExtension lacks APP_GROUPS
                    Add them on developer.apple.com → Identifiers before the archive
                    is exported. Every signing path is blocked until then.
  — signing A       no Apple Distribution identity in this keychain
  ? signing B       needs an Admin key; this key's role can't be read. Confirmed by
                    the local export check after archiving.
  ✔ signing C       Xcode Organizer, with an Admin/Account Holder Apple account
```

Persist the result to `state.json` as `release.preflight` (statuses and messages only — **never a key, key id or issuer id**). A ✗ becomes an `open_risks` entry that leads with the impact: "the 3.0.0 build can't be signed for the App Store until the App IDs have App Groups and Associated Domains", not "preflight failed".

## What the preflight never does

- It never reads, prints, copies or stores the API key, the key id or the issuer id. It checks the variables are set and passes the key **path** to `openssl`.
- It never creates or modifies anything in the developer account or App Store Connect.
- It never fails the run. A ✗ narrows what the run can do (listing sync only, or Organizer upload only), and the checkpoint says so.
