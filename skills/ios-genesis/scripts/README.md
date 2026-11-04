# ios-genesis release scripts

Scripts the release run uses (`references/release-flow.md`). Generalized from the Cadenza 3.0.0 release. Resolve them relative to this skill's directory, never the target project's working directory.

| Script | Writes? | What it does |
|---|---|---|
| `asc_sync.py` | Only `sync --apply` and `attach-build --apply`, each behind a typed confirmation | App Store Connect API: `check` (offline lint), `preflight` (credentials, App ID capabilities, signing paths), `plan` (dry run), `sync` (version, text, review notes, screenshots), `builds`, `attach-build`. **It can't submit, release, or start a PPO test, and no such path may be added.** |
| `release_audit.py` | Never | `archive`: versions, signing, entitlements, privacy manifest and DEBUG strings for every bundle in an `.xcarchive`. `reasons`: required-reason APIs used vs declared, per target. `network`: network code sites. |
| `aso_rank.py` | Never | Keyword rank and competition from the public iTunes Search API. |
| `screenshots/capture.sh` | PNGs under `--out` | Simulator raws through the DEBUG router (`-ios-genesis-screen`), per locale and per Duo display. A **template**: copy it into the project. |
| `screenshots/compose.py` | PNGs under the config's folder | Captioned screenshots for every slot, Duo sets, and header/search creatives from `shots.json`. A **template**: copy it into the project with a `shots.json` (start from `shots.example.json`); the look is project-specific. |

## Credentials

`asc_sync.py` reads `ASC_KEY_PATH`, `ASC_KEY_ID` and `ASC_ISSUER_ID` from the environment and nothing else. The `.p8` is passed by path to `openssl dgst -sign`; no script reads, copies or prints it. Never write a key, key id or issuer id into a config, a doc, `state.json`, a commit or a dispatch prompt.

Key setup, for the user: App Store Connect → Users and Access → Integrations → App Store Connect API → generate a key. Keep the `.p8` outside every repo (`~/.appstoreconnect/private_keys/`, folder `700`, file `600`) and export the three variables in the shell profile.

| Key role | Listing sync | Build upload with `-allowProvisioningUpdates` (cloud signing) |
|---|---|---|
| App Manager | ✔ | ✗ "Cloud signing permission error" (what Cadenza 3.0.0 hit) |
| Admin | ✔ | ✔ if every App ID has every capability its entitlements use |

## Per-project config

`asc_sync.py` reads `<repo>/scripts/asc/asc-config.json` (copy `asc-config.example.json`). It holds the app id, the locales, the file paths, the screenshot slots, `banned_terms`, and `targets` (every bundle id with its entitlements file, extensions included). It holds no secrets and is committed.

Metadata format (`docs/appstore-metadata.md`, template in `templates/appstore-metadata.md`): one `## <locale>` section per locale, and under it `### App Name`, `### Subtitle`, `### Promotional Text`, `### Keywords`, `### Description` and `### What's New`. Each value is the first fenced block under the heading, or else the first inline code span. Review notes (`docs/app-review-notes.md`) are the block between the first two `---` lines.
