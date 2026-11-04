#!/usr/bin/env python3
"""Sync an app's App Store listing from its repo to App Store Connect.

Generalized from Cadenza's scripts/asc/asc_sync.py (3.0.0 release). Python 3
standard library plus the system `openssl`; nothing to install.

Source of truth, all in the target repo and named by the config file:
  metadata      docs/appstore-metadata.md   (## <locale> / ### <Field> sections)
  review_notes  docs/app-review-notes.md    (the block between the first two --- rules)
  screenshots   docs/appstore-screenshots/<locale set>/<slot dir>/*.png

Credentials come only from the environment, never from the config or the repo:
  ASC_KEY_PATH   path to the AuthKey_<KEYID>.p8 file (never read by this
                 script; only passed by path to `openssl dgst -sign`)
  ASC_KEY_ID     the key id
  ASC_ISSUER_ID  the issuer id

Every command is read-only except `sync --apply` and `attach-build --apply`,
which also need a typed confirmation (or --yes). There is deliberately no code
path that submits a version for review, releases it, or starts a Product Page
Optimization test, and none may be added: submission is always the user's act
in App Store Connect.

Usage (run from the target repo, or pass --root):
  asc_sync.py check                          # offline lint: limits, trademarks, screenshots
  asc_sync.py preflight --version 3.0.0      # read-only: credentials, app access, signing readiness
  asc_sync.py plan --version 3.0.0           # read-only dry run of `sync`
  asc_sync.py plan --version 3.0.0 --text-only
  asc_sync.py sync --version 3.0.0 --apply   # create the version if needed, write text + screenshots
  asc_sync.py builds --version 3.0.0         # read-only: uploaded builds and their processing state
  asc_sync.py attach-build --version 3.0.0 --build 1 --apply
"""
import argparse
import base64
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.appstoreconnect.apple.com"
DEFAULT_CONFIG = "scripts/asc/asc-config.json"

# Screenshot display type -> (slot folder, exact pixel size). App Store Connect
# accepted these for Cadenza 2.0.0 (all three reached assetDeliveryState
# COMPLETE). Apple rejects a wrong size for a slot at processing time, so a
# project can override this map in its config if Apple changes them.
DEFAULT_SLOTS = {
    "APP_IPHONE_67": ["6.9-inch-1320x2868", [1320, 2868]],
    "APP_IPHONE_65": ["6.7-inch-1284x2778", [1284, 2778]],
    # "iPhone with Dynamic Island (medium display)" in App Store Connect.
    "APP_IPHONE_61": ["6.3-inch-1206x2622", [1206, 2622]],
}
# iPhone Duo has no ScreenshotDisplayType in the API yet: Duo sets are
# uploaded by hand in App Store Connect's iPhone Duo tab.
MAX_SHOTS_PER_SET = 10
LIMITS = {"name": 30, "subtitle": 30, "promotionalText": 170, "keywords": 100,
          "description": 4000, "whatsNew": 4000, "notes": 4000}
HEADINGS = {"App Name": "name", "Subtitle": "subtitle", "Promotional Text": "promotionalText",
            "Keywords": "keywords", "Description": "description", "What's New": "whatsNew"}
# Guideline 5.2.5: no Apple trademarks in the name, subtitle or keywords.
# Factual compatibility text in the description is allowed.
APPLE_TRADEMARKS = ["apple", "airpods", "iphone", "ipad", "ipod", "apple watch", "watchos",
                    "ios", "ipados", "macos", "mac", "siri", "healthkit", "homekit", "carplay",
                    "facetime", "imessage", "icloud", "apple pay", "app store", "testflight",
                    "vision pro", "visionos", "airtag", "homepod", "apple tv"]
TRADEMARK_FIELDS = ("name", "subtitle", "keywords")

# Entitlement key -> App ID capability type (bundleIdCapabilities). A distribution
# export fails ("no profiles found", "Cloud signing permission error") when an
# entitlement's capability is missing from any App ID, extensions included.
CAPABILITIES = {
    "com.apple.security.application-groups": "APP_GROUPS",
    "com.apple.developer.associated-domains": "ASSOCIATED_DOMAINS",
    "com.apple.developer.healthkit": "HEALTHKIT",
    "aps-environment": "PUSH_NOTIFICATIONS",
    "com.apple.developer.icloud-container-identifiers": "ICLOUD",
    "com.apple.developer.icloud-services": "ICLOUD",
    "com.apple.developer.ubiquity-kvstore-identifier": "ICLOUD",
    "com.apple.developer.in-app-payments": "APPLE_PAY",
    "com.apple.developer.applesignin": "APPLE_ID_AUTH",
    "com.apple.developer.siri": "SIRIKIT",
    "com.apple.developer.homekit": "HOMEKIT",
    "com.apple.developer.networking.wifi-info": "ACCESS_WIFI_INFORMATION",
    "com.apple.developer.default-data-protection": "DATA_PROTECTION",
    "com.apple.developer.usernotifications.time-sensitive": "USERNOTIFICATIONS_TIMESENSITIVE",
    "com.apple.developer.weatherkit": "WEATHERKIT",
    "com.apple.developer.family-controls": "FAMILY_CONTROLS",
    "com.apple.developer.nfc.readersession.formats": "NFC_TAG_READING",
    "com.apple.developer.game-center": "GAME_CENTER",
    "com.apple.developer.pass-type-identifiers": "WALLET",
    "com.apple.developer.associated-appclip-app-identifiers": "APP_CLIPS",
}
# Entitlements every App ID has, or that need no capability.
IMPLICIT_ENTITLEMENTS = {"keychain-access-groups", "application-identifier",
                         "com.apple.developer.team-identifier", "get-task-allow",
                         "com.apple.developer.healthkit.access",
                         "com.apple.developer.healthkit.background-delivery"}


# ---------------------------------------------------------------- config

class Config:
    def __init__(self, root, path):
        self.root = root
        self.path = path
        if not path.exists():
            sys.exit(f"No config at {path}. Copy asc-config.example.json from the ios-genesis "
                     "scripts directory and fill it in (it holds no secrets).")
        raw = json.loads(path.read_text())
        self.app_id = str(raw["app_id"])
        self.platform = raw.get("platform", "IOS")
        self.metadata = root / raw.get("metadata", "docs/appstore-metadata.md")
        self.review_notes = root / raw.get("review_notes", "docs/app-review-notes.md")
        self.shots_dir = root / raw.get("screenshots_dir", "docs/appstore-screenshots")
        self.shot_glob = raw.get("screenshot_glob", "*.png")
        self.primary_locale = raw.get("primary_locale", "en-US")
        # locale -> {"heading": "## en-US", "screenshots": "<set dir>"}
        self.locales = raw.get("locales") or {self.primary_locale: {}}
        self.slots = {k: (v[0], tuple(v[1])) for k, v in (raw.get("slots") or DEFAULT_SLOTS).items()}
        self.banned_terms = [t.lower() for t in raw.get("banned_terms", [])]
        # [{"bundle_id": "...", "entitlements": "App/App.entitlements"}, ...]
        self.targets = raw.get("targets", [])

    def heading(self, locale):
        return self.locales[locale].get("heading", f"## {locale}")

    def shot_set(self, locale):
        return self.locales[locale].get("screenshots", locale)


# ---------------------------------------------------------------- auth / http

def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


_TOKEN = {"value": None, "exp": 0}


def credentials():
    values = {k: os.environ.get(k) for k in ("ASC_KEY_PATH", "ASC_KEY_ID", "ASC_ISSUER_ID")}
    missing = [k for k, v in values.items() if not v]
    if missing:
        sys.exit("Set " + ", ".join(missing) + " in the environment. The key, key id and issuer id "
                 "never go in the config or the repo.")
    return values["ASC_KEY_PATH"], values["ASC_KEY_ID"], values["ASC_ISSUER_ID"]


def _token():
    now = int(time.time())
    if _TOKEN["value"] and now < _TOKEN["exp"] - 60:
        return _TOKEN["value"]
    key, kid, iss = credentials()
    msg = (_b64(json.dumps({"alg": "ES256", "kid": kid, "typ": "JWT"}).encode()) + b"." +
           _b64(json.dumps({"iss": iss, "iat": now, "exp": now + 900, "aud": "appstoreconnect-v1"}).encode()))
    der = subprocess.run(["openssl", "dgst", "-sha256", "-sign", key], input=msg,
                         capture_output=True, check=True).stdout
    _TOKEN.update(value=(msg + b"." + _b64(_der_to_raw(der))).decode(), exp=now + 900)
    return _TOKEN["value"]


def _der_to_raw(der):
    """DER-encoded ECDSA signature (SEQUENCE of two INTEGERs) -> raw r||s,
    32 bytes each, as JWS ES256 expects."""
    def length(pos):
        first = der[pos]
        if first < 0x80:
            return first, pos + 1
        n = first & 0x7F
        return int.from_bytes(der[pos + 1:pos + 1 + n], "big"), pos + 1 + n

    if not der or der[0] != 0x30:
        sys.exit("openssl returned an unexpected signature format (not a DER SEQUENCE)")
    _, pos = length(1)
    parts = []
    for _ in range(2):
        if der[pos] != 0x02:
            sys.exit("openssl returned an unexpected signature format (expected INTEGER)")
        n, pos = length(pos + 1)
        value = der[pos:pos + n].lstrip(b"\0")
        if len(value) > 32:
            sys.exit("openssl returned a signature integer longer than 32 bytes (is the key P-256?)")
        parts.append(value.rjust(32, b"\0"))
        pos += n
    return parts[0] + parts[1]


class ApiError(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def call(method, path, body=None, retries=3, soft=False):
    """One API request. Retries 429 (never processed) for any method; retries
    5xx and network errors only for GET, since a write may have been applied
    before the error and repeating it could create a duplicate. With soft=True
    an HTTP error raises ApiError instead of exiting, for read-only probes."""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + _token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429 or (e.code >= 500 and method == "GET"):
                time.sleep(2 ** attempt * 2)
                continue
            if e.code == 404 and method == "DELETE":
                return {}  # already gone
            try:
                errs = json.load(e).get("errors", [])
                detail = "; ".join(f"{x.get('title')}: {x.get('detail')}" for x in errs)
            except Exception:
                detail = str(e)
            if soft:
                raise ApiError(e.code, detail)
            sys.exit(f"{method} {path} failed ({e.code}): {detail}")
        except urllib.error.URLError as e:
            if method == "GET" and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            sys.exit(f"{method} {path} failed: network error ({e.reason}). "
                     "A write may or may not have been applied; run `plan` to see the current state.")
    sys.exit(f"{method} {path} failed after {retries} attempts")


def get(path, soft=False):
    return call("GET", path, soft=soft)


# ---------------------------------------------------------------- repo source

def parse_metadata(cfg):
    text = cfg.metadata.read_text()
    out = {}
    for locale in cfg.locales:
        marker = cfg.heading(locale)
        start = text.find(marker)
        if start == -1:
            sys.exit(f"No `{marker}` section in {cfg.metadata.relative_to(cfg.root)}")
        end = text.find("\n## ", start + len(marker))
        section = text[start:end if end != -1 else None]
        fields = {}
        for m in re.finditer(r"^### (.+)$", section, re.M):
            key = next((v for k, v in HEADINGS.items() if m.group(1).startswith(k)), None)
            if not key:
                continue
            rest = section[m.end():]
            nxt = re.search(r"^#{2,3} ", rest, re.M)
            block = rest[:nxt.start()] if nxt else rest
            fence = re.search(r"```\n(.*?)\n```", block, re.S)
            inline = re.search(r"`([^`\n]+)`", block)
            if fence:
                fields[key] = fence.group(1).strip()
            elif inline:
                fields[key] = inline.group(1).strip()
        out[locale] = fields
    return out


def parse_review_notes(cfg):
    """The paste-ready block: everything between the first two `---` rules."""
    parts = re.split(r"^---$", cfg.review_notes.read_text(), flags=re.M)
    if len(parts) < 3:
        sys.exit(f"Couldn't find the notes block between --- rules in {cfg.review_notes.relative_to(cfg.root)}")
    return parts[1].strip()


def shots(cfg, locale, slot_dir, required=True):
    folder = cfg.shots_dir / cfg.shot_set(locale) / slot_dir
    files = sorted(folder.glob(cfg.shot_glob))
    if not files and required:
        sys.exit(f"No screenshots in {folder}")
    return files


def png_problem(path, size):
    """Why App Store Connect would reject this file for the slot, or None."""
    head = path.read_bytes()[:26]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return "not a PNG"
    w, h = int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if (w, h) != tuple(size):
        return f"{w}x{h}, expected {size[0]}x{size[1]}"
    if head[25] in (4, 6):
        return "has an alpha channel"
    return None


# ---------------------------------------------------------------- check (offline)

def _words(text):
    return [w for w in re.split(r"[^\w']+", (text or "").lower()) if w]


def check(cfg, quiet=False, screenshots=True):
    """Offline lint. Returns the list of blocking problems; warnings print only.
    screenshots=False skips the image checks (a --text-only sync never sends them)."""
    problems, warnings = [], []
    meta = parse_metadata(cfg)
    for loc, fields in meta.items():
        for f, v in fields.items():
            if len(v) > LIMITS[f]:
                problems.append(f"{loc} {f} is {len(v)} > {LIMITS[f]} characters")
        for f in TRADEMARK_FIELDS:
            low = " " + " ".join(_words(fields.get(f, ""))) + " "
            for term in APPLE_TRADEMARKS:
                if f" {term} " in low:
                    problems.append(f"{loc} {f} contains the Apple trademark \"{term}\" (Guideline 5.2.5)")
        for f, v in fields.items():
            low = v.lower()
            for term in cfg.banned_terms:
                if term in low:
                    problems.append(f"{loc} {f} names \"{term}\" (banned_terms: other platforms' names "
                                    "and logos stay out of the listing)")
        kw = fields.get("keywords", "")
        if kw:
            if re.search(r",\s|\s,", kw):
                warnings.append(f"{loc} keywords have spaces around commas (wasted characters)")
            parts = [p.strip().lower() for p in kw.split(",") if p.strip()]
            dupes = sorted({p for p in parts if parts.count(p) > 1})
            if dupes:
                warnings.append(f"{loc} keywords repeat: {', '.join(dupes)}")
            indexed = set(_words(fields.get("name", "")) + _words(fields.get("subtitle", "")))
            overlap = sorted(set(parts) & indexed)
            if overlap:
                warnings.append(f"{loc} keywords repeat words already in the name/subtitle: {', '.join(overlap)}")
        for f in ("name", "subtitle", "keywords", "description"):
            if f not in fields:
                warnings.append(f"{loc} has no {f} in {cfg.metadata.name}")
    notes = parse_review_notes(cfg)
    if len(notes) > LIMITS["notes"]:
        problems.append(f"review notes are {len(notes)} > {LIMITS['notes']} characters")
    for loc in (cfg.locales if screenshots else []):
        for dtype, (slot_dir, size) in cfg.slots.items():
            files = shots(cfg, loc, slot_dir, required=False)
            if not files:
                warnings.append(f"{loc} {dtype}: no screenshots in {cfg.shot_set(loc)}/{slot_dir}")
            if len(files) > MAX_SHOTS_PER_SET:
                problems.append(f"{loc} {dtype}: {len(files)} screenshots > {MAX_SHOTS_PER_SET}")
            for f in files:
                why = png_problem(f, size)
                if why:
                    problems.append(f"{f.relative_to(cfg.root)}: {why}")
    if not quiet:
        print(f"[check] {cfg.metadata.relative_to(cfg.root)}, {cfg.review_notes.relative_to(cfg.root)} "
              f"({len(notes)}/{LIMITS['notes']}), screenshots under {cfg.shots_dir.relative_to(cfg.root)}")
        for loc, fields in meta.items():
            print(f"  {loc}: " + ", ".join(f"{f} {len(v)}/{LIMITS[f]}" for f, v in fields.items()))
        for w in warnings:
            print(f"  ! {w}")
        for p in problems:
            print(f"  ✗ {p}")
        print("  ✔ no blocking problems" if not problems else f"  {len(problems)} blocking problem(s)")
    return problems


# ---------------------------------------------------------------- ASC state

def find_version(cfg, version):
    data = get(f"/v1/apps/{cfg.app_id}/appStoreVersions?filter[versionString]={version}"
               f"&filter[platform]={cfg.platform}&limit=1")["data"]
    return data[0] if data else None


def editable_app_info(cfg):
    infos = get(f"/v1/apps/{cfg.app_id}/appInfos")["data"]
    live = {"READY_FOR_SALE", "READY_FOR_DISTRIBUTION"}
    for info in infos:
        state = info["attributes"].get("state") or info["attributes"].get("appStoreState")
        if state not in live:
            return info
    return None


def by_locale(items):
    return {x["attributes"]["locale"]: x for x in items}


# ---------------------------------------------------------------- plan / apply

def diff_line(field, cur, new):
    n = len(new or "")
    limit = LIMITS.get(field)
    over = "  ** OVER LIMIT **" if limit and n > limit else ""
    if (cur or "") == (new or ""):
        return f"    = {field} ({n}/{limit}) unchanged"
    short = lambda s: (s or "∅").replace("\n", "⏎")[:70] + ("…" if s and len(s) > 70 else "")
    return f"    ~ {field} ({n}/{limit}){over}\n        now: {short(cur)}\n        new: {short(new)}"


def sync(cfg, version_string, apply, text_only=False):
    if check(cfg, quiet=True, screenshots=not text_only):
        check(cfg, screenshots=not text_only)
        sys.exit("Fix the blocking problems above first; nothing was sent.")
    meta = parse_metadata(cfg)
    print(f"Source: {cfg.metadata.relative_to(cfg.root)} — locales {', '.join(meta)}")

    version = find_version(cfg, version_string)
    print(f"\n[version] {cfg.platform} {version_string}: " + (
        f"exists ({version['attributes']['appStoreState']})" if version else "does not exist → will create"))
    if apply and not version:
        version = call("POST", "/v1/appStoreVersions", {"data": {
            "type": "appStoreVersions",
            "attributes": {"platform": cfg.platform, "versionString": version_string},
            "relationships": {"app": {"data": {"type": "apps", "id": cfg.app_id}}}}})["data"]
        print(f"    created {version['id']}")

    # App info (name, subtitle): editable only once a new version exists.
    info = editable_app_info(cfg)
    print("\n[app info] " + ("editable record found" if info else
          "no editable record yet (Apple creates one with the new version)"))
    info_locs = by_locale(get(f"/v1/appInfos/{info['id']}/appInfoLocalizations")["data"]) if info else {}
    info_locs_live = {}
    if not info:
        live = get(f"/v1/apps/{cfg.app_id}/appInfos")["data"][0]
        info_locs_live = by_locale(get(f"/v1/appInfos/{live['id']}/appInfoLocalizations")["data"])
    for loc, fields in meta.items():
        cur = (info_locs if info else info_locs_live).get(loc)
        print(f"  {loc}" + ("" if cur else "  (localization missing → will create)"))
        for f in ("name", "subtitle"):
            print(diff_line(f, cur["attributes"].get(f) if cur else None, fields.get(f)))
        if apply and info:
            attrs = {f: fields[f] for f in ("name", "subtitle") if f in fields}
            if cur:
                call("PATCH", f"/v1/appInfoLocalizations/{cur['id']}", {"data": {
                    "type": "appInfoLocalizations", "id": cur["id"], "attributes": attrs}})
            else:
                call("POST", "/v1/appInfoLocalizations", {"data": {
                    "type": "appInfoLocalizations", "attributes": {"locale": loc, **attrs},
                    "relationships": {"appInfo": {"data": {"type": "appInfos", "id": info["id"]}}}}})

    # Version localizations (description, keywords, promo, what's new).
    ver_locs = by_locale(get(f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations")["data"]) \
        if version else {}
    print("\n[version text]")
    for loc, fields in meta.items():
        cur = ver_locs.get(loc)
        print(f"  {loc}" + ("" if cur else "  (localization missing → will create)"))
        for f in ("promotionalText", "keywords", "description", "whatsNew"):
            print(diff_line(f, cur["attributes"].get(f) if cur else None, fields.get(f)))
        if apply:
            attrs = {f: fields[f] for f in ("promotionalText", "keywords", "description", "whatsNew") if f in fields}
            if cur:
                call("PATCH", f"/v1/appStoreVersionLocalizations/{cur['id']}", {"data": {
                    "type": "appStoreVersionLocalizations", "id": cur["id"], "attributes": attrs}})
            else:
                primary = ver_locs.get(cfg.primary_locale)
                if primary and primary["attributes"].get("supportUrl"):
                    attrs["supportUrl"] = primary["attributes"]["supportUrl"]
                cur = call("POST", "/v1/appStoreVersionLocalizations", {"data": {
                    "type": "appStoreVersionLocalizations", "attributes": {"locale": loc, **attrs},
                    "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions",
                                                                   "id": version["id"]}}}}})["data"]
                ver_locs[loc] = cur

    fill_required_urls(cfg, apply, info, version)
    review_notes(cfg, apply, version)

    if text_only:
        print("\n[screenshots] skipped (--text-only); a new version keeps the previous version's sets")
    else:
        print("\n[screenshots] per-locale sets (iPhone Duo sets are uploaded by hand: no API display type)")
        for loc in meta:
            vl = ver_locs.get(loc)
            existing = {}
            if vl:
                for s in get(f"/v1/appStoreVersionLocalizations/{vl['id']}/appScreenshotSets?limit=50")["data"]:
                    existing[s["attributes"]["screenshotDisplayType"]] = s
            for dtype, (slot_dir, size) in cfg.slots.items():
                files = shots(cfg, loc, slot_dir)
                cur_set = existing.get(dtype)
                cur_n = len(get(f"/v1/appScreenshotSets/{cur_set['id']}/appScreenshots")["data"]) if cur_set else 0
                print(f"  {loc} {dtype}: {cur_n} now → {len(files)} from {cfg.shot_set(loc)}/{slot_dir}")
                if apply and vl:
                    replace_set(vl["id"], dtype, size, cur_set, files)

    if not apply:
        flags = " --text-only" if text_only else ""
        print(f"\nDry run only. Nothing was changed. `sync --version {version_string}{flags} --apply` writes these changes.")
    else:
        print(f"\nDone. Run `plan --version {version_string}` to confirm every field now reads unchanged.")


# URLs App Review requires in every localization. New localizations don't
# inherit them, so copy the primary locale's value wherever one is missing
# (Cadenza 2.0.0 was blocked at submission by an empty es-MX privacy policy URL).
REQUIRED_URLS = (("appInfoLocalizations", "privacyPolicyUrl"),
                 ("appStoreVersionLocalizations", "supportUrl"))


def fill_required_urls(cfg, apply, info, version):
    print(f"\n[required URLs] copied from {cfg.primary_locale} where missing")
    sources = {"appInfoLocalizations": f"/v1/appInfos/{info['id']}/appInfoLocalizations" if info else None,
               "appStoreVersionLocalizations":
                   f"/v1/appStoreVersions/{version['id']}/appStoreVersionLocalizations" if version else None}
    for kind, field in REQUIRED_URLS:
        if not sources[kind]:
            print(f"  {field}: skipped until the version exists")
            continue
        locs = by_locale(get(sources[kind])["data"])
        primary = (locs.get(cfg.primary_locale) or {}).get("attributes", {}).get(field)
        for loc, rec in sorted(locs.items()):
            value = rec["attributes"].get(field)
            if value:
                print(f"    = {loc} {field} set")
            elif not primary:
                print(f"    ! {loc} {field} missing, and {cfg.primary_locale} has none to copy: set it in App Store Connect")
            else:
                print(f"    ~ {loc} {field} missing → {primary}")
                if apply:
                    call("PATCH", f"/v1/{kind}/{rec['id']}", {"data": {
                        "type": kind, "id": rec["id"], "attributes": {field: primary}}})


def review_notes(cfg, apply, version):
    """App Review notes for the version. Updates an existing review detail's
    notes; a missing one also needs contact details, so that's left to App
    Store Connect."""
    notes = parse_review_notes(cfg)
    print(f"\n[review notes] from {cfg.review_notes.relative_to(cfg.root)}")
    if not version:
        print(f"    notes ({len(notes)}/{LIMITS['notes']}): skipped until the version exists")
        return
    detail = get(f"/v1/appStoreVersions/{version['id']}/appStoreReviewDetail").get("data")
    if not detail:
        print("    ! no review detail on this version yet: add contact details in App Store Connect, "
              "then re-run to fill the notes")
        return
    print(diff_line("notes", detail["attributes"].get("notes"), notes))
    if apply and detail["attributes"].get("notes") != notes:
        call("PATCH", f"/v1/appStoreReviewDetails/{detail['id']}", {"data": {
            "type": "appStoreReviewDetails", "id": detail["id"], "attributes": {"notes": notes}}})


def upload(set_id, path):
    data = path.read_bytes()
    shot = call("POST", "/v1/appScreenshots", {"data": {
        "type": "appScreenshots", "attributes": {"fileName": path.name, "fileSize": len(data)},
        "relationships": {"appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": set_id}}}}})["data"]
    for op in shot["attributes"]["uploadOperations"]:
        chunk = data[op["offset"]:op["offset"] + op["length"]]
        req = urllib.request.Request(op["url"], data=chunk, method=op["method"],
                                     headers={h["name"]: h["value"] for h in op["requestHeaders"]})
        urllib.request.urlopen(req).read()
    call("PATCH", f"/v1/appScreenshots/{shot['id']}", {"data": {
        "type": "appScreenshots", "id": shot["id"],
        "attributes": {"uploaded": True, "sourceFileChecksum": hashlib.md5(data).hexdigest()}}})
    for _ in range(30):
        state = get(f"/v1/appScreenshots/{shot['id']}")["data"]["attributes"]["assetDeliveryState"]["state"]
        if state == "COMPLETE":
            return
        if state == "FAILED":
            sys.exit(f"Screenshot {path.name} failed processing")
        time.sleep(2)
    print(f"    warning: {path.name} still processing")


def replace_set(loc_id, dtype, size, cur_set, files):
    for f in files:
        why = png_problem(f, size)
        if why:
            sys.exit(f"{f}: {why}")
    old = get(f"/v1/appScreenshotSets/{cur_set['id']}/appScreenshots")["data"] if cur_set else []
    if cur_set:
        set_id = cur_set["id"]
    else:
        set_id = call("POST", "/v1/appScreenshotSets", {"data": {
            "type": "appScreenshotSets", "attributes": {"screenshotDisplayType": dtype},
            "relationships": {"appStoreVersionLocalization": {"data": {
                "type": "appStoreVersionLocalizations", "id": loc_id}}}}})["data"]["id"]
    # Upload before deleting when the set has room, so a failed upload never
    # leaves the slot empty. A set holds at most 10, so a full swap of 6 onto 6
    # has to delete first; files were validated above to make that safe.
    upload_first = len(old) + len(files) <= MAX_SHOTS_PER_SET
    if not upload_first:
        for s in old:
            call("DELETE", f"/v1/appScreenshots/{s['id']}")
        print(f"    removed {len(old)} old screenshots (set full); if an upload below fails, "
              "re-run `sync --apply` to refill this slot")
    for f in files:
        upload(set_id, f)
        print(f"    uploaded {f.name}")
    if upload_first:
        for s in old:
            call("DELETE", f"/v1/appScreenshots/{s['id']}")
        if old:
            print(f"    removed {len(old)} old screenshots")


# ---------------------------------------------------------------- preflight (read-only)

def _entitlement_keys(path):
    with open(path, "rb") as fh:
        return set(plistlib.load(fh).keys())


def local_distribution_identities():
    try:
        out = subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return [l.strip() for l in out.splitlines() if "Apple Distribution" in l or "iPhone Distribution" in l]


def preflight(cfg, version_string):
    """Read-only. Answers, before anything is archived: can this machine and
    this key get a build signed for distribution and uploaded? Prints a
    verdict per signing path; never creates certificates, profiles or IDs."""
    blockers = []
    key, kid, _ = credentials()
    print("[credentials]")
    print(f"  ✔ ASC_KEY_PATH, ASC_KEY_ID, ASC_ISSUER_ID set (key id {kid})")
    try:
        mode = stat.S_IMODE(os.stat(key).st_mode)
        print(f"  {'✔' if mode & 0o077 == 0 else '!'} key file permissions {oct(mode)}"
              + ("" if mode & 0o077 == 0 else " (chmod 600 it; keep it outside every repo)"))
    except OSError as e:
        sys.exit(f"  ✗ can't stat ASC_KEY_PATH: {e}")

    print("\n[app access]")
    try:
        app = get(f"/v1/apps/{cfg.app_id}", soft=True)["data"]["attributes"]
        print(f"  ✔ {app.get('name')} ({app.get('bundleId')})")
    except ApiError as e:
        sys.exit(f"  ✗ GET app {cfg.app_id} failed ({e}). The key can't see this app: check the app id "
                 "and that the key's role has access to it.")
    if version_string:
        v = find_version(cfg, version_string)
        print(f"  version {version_string}: " + (v["attributes"]["appStoreState"] if v else "not created yet"))

    print("\n[App IDs and capabilities] every target, extensions included")
    can_read_provisioning = True
    store_profiles = {}
    for t in cfg.targets:
        bid = t["bundle_id"]
        ent_path = cfg.root / t["entitlements"] if t.get("entitlements") else None
        ents = _entitlement_keys(ent_path) if ent_path and ent_path.exists() else set()
        needed = {CAPABILITIES[k] for k in ents if k in CAPABILITIES}
        unmapped = sorted(k for k in ents if k not in CAPABILITIES and k not in IMPLICIT_ENTITLEMENTS)
        try:
            ids = get(f"/v1/bundleIds?filter[identifier]={urllib.parse.quote(bid)}&limit=20", soft=True)["data"]
        except ApiError as e:
            if e.code in (401, 403):
                can_read_provisioning = False
                print(f"  ! {bid}: this key can't read provisioning data ({e.code}).")
                break
            raise
        rec = next((x for x in ids if x["attributes"]["identifier"] == bid), None)
        if not rec:
            blockers.append(f"App ID {bid} is not registered")
            print(f"  ✗ {bid}: no App ID registered")
            continue
        caps = {c["attributes"]["capabilityType"] for c in
                get(f"/v1/bundleIds/{rec['id']}/bundleIdCapabilities?limit=50")["data"]}
        missing = sorted(needed - caps)
        print(f"  {'✗' if missing else '✔'} {bid}: entitlements need {', '.join(sorted(needed)) or 'no capabilities'}"
              + (f"; MISSING on the App ID: {', '.join(missing)}" if missing else ""))
        for k in unmapped:
            print(f"      ? entitlement {k}: not mapped to a capability, check it by hand")
        if missing:
            blockers.append(f"{bid} lacks {', '.join(missing)} (add on developer.apple.com → Identifiers)")
        profiles = get(f"/v1/bundleIds/{rec['id']}/profiles?limit=50")["data"]
        active = [p["attributes"]["name"] for p in profiles
                  if p["attributes"].get("profileType") == "IOS_APP_STORE"
                  and p["attributes"].get("profileState") == "ACTIVE"]
        store_profiles[bid] = active
        print(f"      App Store profiles (active): {', '.join(active) or 'none'}")

    identities = local_distribution_identities()
    print("\n[signing paths]")
    if identities is None:
        print("  ? couldn't run `security find-identity` (not on macOS?)")
    else:
        print(f"  local distribution identities in the keychain: {len(identities)}")
    local_ok = bool(identities) and can_read_provisioning and cfg.targets and \
        all(store_profiles.get(t["bundle_id"]) for t in cfg.targets)
    print(f"  {'✔' if local_ok else '—'} A. local signing (Apple Distribution identity + an active App Store "
          "profile per bundle ID)" + ("" if local_ok else ": not ready"))
    if can_read_provisioning:
        print("  ? B. cloud signing (-allowProvisioningUpdates with the API key): needs an Admin key, "
              "because cloud-managed distribution certificates are Admin-only for API keys. The API can't "
              "report a key's role, so this is confirmed only by the local export check after archiving.")
    else:
        print("  ✗ B. cloud signing: a key that can't read provisioning can't cloud-sign either "
              "(\"Cloud signing permission error\"). Use an Admin key, or path C.")
    print("  ✔ C. Xcode Organizer: Distribute App → App Store Connect → Upload, signed in with an Apple "
          "account that is Admin/Account Holder or has \"Access to Cloud Managed Distribution Certificate\".")
    if not cfg.targets:
        print("\n  ! no `targets` in the config: App ID capability checks were skipped")

    print()
    if blockers:
        print("Blockers (fix before archiving for distribution):")
        for b in blockers:
            print(f"  ✗ {b}")
        sys.exit(1)
    print("No blockers found. Prove the signing path with a local export (destination `export`) after archiving.")


# ---------------------------------------------------------------- builds

def list_builds(cfg, version_string):
    data = get(f"/v1/builds?filter[app]={cfg.app_id}&filter[preReleaseVersion.version]={version_string}"
               "&sort=-uploadedDate&limit=20")["data"]
    print(f"[builds] {version_string}: {len(data)} uploaded")
    for b in data:
        a = b["attributes"]
        print(f"  build {a.get('version')}: {a.get('processingState')}, uploaded {a.get('uploadedDate')}, "
              f"usesNonExemptEncryption={a.get('usesNonExemptEncryption')}, expired={a.get('expired')}")
    return data


def attach_build(cfg, version_string, build_number, apply):
    version = find_version(cfg, version_string)
    if not version:
        sys.exit(f"Version {version_string} doesn't exist in App Store Connect; run `sync --apply` first.")
    builds = [b for b in list_builds(cfg, version_string) if b["attributes"].get("version") == str(build_number)]
    if not builds:
        sys.exit(f"No uploaded build {build_number} for {version_string}.")
    build = builds[0]
    state = build["attributes"].get("processingState")
    if state != "VALID":
        sys.exit(f"Build {build_number} is {state}; wait until it's VALID (processing can take a while).")
    print(f"\n[attach] build {build_number} → version {version_string} ({version['attributes']['appStoreState']})")
    if not apply:
        print("Dry run only. `attach-build ... --apply` attaches it. Submitting stays manual.")
        return
    call("PATCH", f"/v1/appStoreVersions/{version['id']}/relationships/build",
         {"data": {"type": "builds", "id": build["id"]}})
    print("    attached. The version is NOT submitted; that's the user's step in App Store Connect.")


# ---------------------------------------------------------------- main

def confirm(args, what):
    if not args.apply:
        return False
    if args.yes:
        return True
    reply = input(f"This will {what} in App Store Connect. Type 'apply' to continue: ")
    if reply.strip() != "apply":
        sys.exit("Cancelled.")
    return True


def repo_root(arg):
    if arg:
        return Path(arg).resolve()
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", default="plan",
                   choices=["check", "preflight", "plan", "sync", "builds", "attach-build"])
    p.add_argument("--root", help="target repo root (default: git toplevel of the cwd)")
    p.add_argument("--config", help=f"config path (default: <root>/{DEFAULT_CONFIG})")
    p.add_argument("--version", dest="version_string", help="marketing version, e.g. 3.0.0")
    p.add_argument("--build", help="build number, for attach-build")
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    p.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    p.add_argument("--text-only", action="store_true",
                   help="sync text and review notes only; leave screenshots untouched")
    args = p.parse_args()
    root = repo_root(args.root)
    cfg = Config(root, Path(args.config).resolve() if args.config else root / DEFAULT_CONFIG)

    if args.command == "check":
        sys.exit(1 if check(cfg) else 0)
    if args.command == "preflight":
        preflight(cfg, args.version_string)
        return
    if not args.version_string:
        sys.exit("--version is required for this command")
    if args.command == "builds":
        list_builds(cfg, args.version_string)
    elif args.command == "attach-build":
        if not args.build:
            sys.exit("--build is required for attach-build")
        attach_build(cfg, args.version_string, args.build,
                     confirm(args, f"attach build {args.build} to version {args.version_string}"))
    else:
        if args.command == "plan":
            if args.apply:
                print("`plan` is always a dry run; use `sync --apply` to write.\n")
            args.apply = False
        what = f"create/update version {args.version_string} text and review notes" + (
            "" if args.text_only else " and replace its screenshots")
        sync(cfg, args.version_string, confirm(args, what), text_only=args.text_only)


if __name__ == "__main__":
    main()
