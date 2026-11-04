#!/usr/bin/env python3
"""Release-only checks for an iOS app: things a Debug simulator build never shows.

Read-only. Never edits the project, never signs, never uploads.

  release_audit.py archive <App.xcarchive> --expect-version 3.0.0 --expect-build 1 \
      [--debug-marker DebugRouter --debug-marker FixtureSeed ...]
      Every bundle in the archive (app, app extensions, App Clips, watch apps):
      version/build match, bundle id, signing authority, `codesign --verify
      --deep --strict`, entitlements, a PrivacyInfo.xcprivacy in the bundle,
      and `strings` on the executable for DEBUG-only routes and fixtures.

  release_audit.py reasons --target App App/PrivacyInfo.xcprivacy App Shared \
                           --target ShareExt ShareExt/PrivacyInfo.xcprivacy ShareExt Shared/Inbox
      Greps each target's sources for required-reason APIs (UserDefaults, file
      timestamps, boot time, disk space, active keyboards) and compares them to
      the categories that target's manifest declares. List every source dir a
      target compiles, including shared folders compiled into an extension.

  release_audit.py network <dir> [<dir> ...]
      Lists network code (URLSession, NWConnection, WKWebView, URL literals,
      analytics SDK imports) so the listing's and privacy label's claims can be
      checked against it.

Exit status 1 when a blocking finding is printed (✗), 0 otherwise.
"""
import argparse
import plistlib
import re
import subprocess
import sys
from pathlib import Path

# Markers the ios-genesis debug router and its fixtures leave in a binary
# compiled without `#if DEBUG` guards. Projects add their own with --debug-marker.
DEFAULT_DEBUG_MARKERS = ["ios-genesis-screen", "DebugRouter", "DebugRegistry"]

# Required-reason API categories -> source patterns. Apple's list:
# developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api
REASON_APIS = {
    "NSPrivacyAccessedAPICategoryUserDefaults": [
        r"\bUserDefaults\b", r"\bNSUserDefaults\b", r"@AppStorage\b"],
    "NSPrivacyAccessedAPICategoryFileTimestamp": [
        r"\bcreationDate\b", r"\bmodificationDate\b", r"\bcontentModificationDate(Key)?\b",
        r"\bcreationDateKey\b", r"\bcontentAccessDate(Key)?\b", r"\bNSFile(Creation|Modification)Date\b",
        r"\.fileModificationDate\b", r"\bgetattrlist\b", r"\b(f|l)?stat\(", r"\battributesOfItem\b"],
    "NSPrivacyAccessedAPICategorySystemBootTime": [
        r"\bsystemUptime\b", r"\bmach_absolute_time\b"],
    "NSPrivacyAccessedAPICategoryDiskSpace": [
        r"\bvolumeAvailableCapacity\w*\b", r"\bvolumeTotalCapacityKey\b", r"\bNSFileSystem(Free)?Size\b",
        r"\bsystemFreeSize\b", r"\bstatv?fs\("],
    "NSPrivacyAccessedAPICategoryActiveKeyboards": [r"\bactiveInputModes\b"],
}
NETWORK_PATTERNS = [r"\bURLSession\b", r"\bURLRequest\b", r"\bNWConnection\b", r"\bNWPathMonitor\b",
                    r"\bWKWebView\b", r"\bSFSafariViewController\b", r"\bCFNetwork\b",
                    r"\"https?://", r"^\s*import\s+(Firebase\w*|Amplitude|Mixpanel|Sentry|Segment\w*|"
                    r"FBSDK\w*|AppsFlyer\w*|GoogleMobileAds|Bugsnag)\b"]
SOURCE_SUFFIXES = {".swift", ".m", ".mm", ".c", ".h"}

failures = 0


def ok(msg):
    print(f"  ✔ {msg}")


def warn(msg):
    print(f"  ! {msg}")


def fail(msg):
    global failures
    failures += 1
    print(f"  ✗ {msg}")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


# ---------------------------------------------------------------- archive

def bundles(archive):
    apps = sorted((archive / "Products" / "Applications").glob("*.app"))
    if not apps:
        sys.exit(f"No .app under {archive}/Products/Applications (is this an .xcarchive?)")
    found = []
    for app in apps:
        found.append(app)
        for sub in ("PlugIns", "Extensions", "AppClips", "Watch"):
            found.extend(sorted((app / sub).glob("*.app*")))
    return found


def audit_bundle(bundle, args):
    print(f"\n[{bundle.name}]")
    info_path = bundle / "Info.plist"
    with open(info_path, "rb") as fh:
        info = plistlib.load(fh)
    version, build = info.get("CFBundleShortVersionString"), info.get("CFBundleVersion")
    bid = info.get("CFBundleIdentifier")
    line = f"{bid} {version} ({build})"
    if (args.expect_version and version != args.expect_version) or (args.expect_build and build != args.expect_build):
        fail(f"{line}: expected {args.expect_version} ({args.expect_build}); app and extensions must match")
    else:
        ok(line)

    verify = run(["codesign", "--verify", "--deep", "--strict", str(bundle)])
    (ok if verify.returncode == 0 else fail)("codesign --verify --deep --strict" +
                                             ("" if verify.returncode == 0 else f": {verify.stderr.strip()}"))
    details = run(["codesign", "-dvv", str(bundle)]).stderr
    authority = next((l.split("=", 1)[1] for l in details.splitlines() if l.startswith("Authority=")), "unsigned")
    if authority.startswith("Apple Development"):
        warn(f"signed {authority}: fine for the archive; the App Store export re-signs for distribution")
    else:
        ok(f"signed {authority}")

    ents = run(["codesign", "-d", "--entitlements", "-", "--xml", str(bundle)])
    try:
        ent = plistlib.loads(ents.stdout.encode()) if ents.stdout.strip() else {}
    except Exception:
        ent = {}
    keys = sorted(k for k in ent if k not in ("application-identifier", "com.apple.developer.team-identifier"))
    print(f"    entitlements: {', '.join(keys) or 'none'}")
    if ent.get("get-task-allow"):
        warn("get-task-allow is true (a development signature; the distribution export removes it)")

    manifest = bundle / "PrivacyInfo.xcprivacy"
    if manifest.exists():
        with open(manifest, "rb") as fh:
            cats = sorted(t.get("NSPrivacyAccessedAPIType", "?")
                          for t in plistlib.load(fh).get("NSPrivacyAccessedAPITypes", []))
        ok("PrivacyInfo.xcprivacy present: " + (", ".join(c.replace("NSPrivacyAccessedAPICategory", "")
                                                         for c in cats) or "no required-reason APIs declared"))
    else:
        fail("no PrivacyInfo.xcprivacy in this bundle (every target that uses a required-reason API needs its own)")

    exe = bundle / info.get("CFBundleExecutable", bundle.stem)
    if exe.exists():
        text = run(["strings", "-a", str(exe)]).stdout
        hits = [m for m in DEFAULT_DEBUG_MARKERS + (args.debug_marker or []) if m in text]
        if hits:
            fail(f"DEBUG-only strings in the Release binary: {', '.join(hits)} (guard them with #if DEBUG)")
        else:
            ok(f"no DEBUG markers in {exe.name} ({len(DEFAULT_DEBUG_MARKERS) + len(args.debug_marker or [])} checked)")
    else:
        warn(f"executable {exe.name} not found; strings check skipped")


def cmd_archive(args):
    archive = Path(args.archive)
    info_plist = archive / "Info.plist"
    if info_plist.exists():
        with open(info_plist, "rb") as fh:
            meta = plistlib.load(fh)
        print(f"[archive] {archive.name}: {meta.get('Name')} created {meta.get('CreationDate')}")
    for b in bundles(archive):
        audit_bundle(b, args)


# ---------------------------------------------------------------- reasons

def sources(dirs):
    for d in dirs:
        for p in Path(d).rglob("*"):
            if p.suffix in SOURCE_SUFFIXES and "Tests" not in p.parts:
                yield p


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def cmd_reasons(args):
    for name, manifest, *dirs in args.target:
        print(f"\n[{name}] {manifest} ← {', '.join(dirs)}")
        declared = set()
        if Path(manifest).exists():
            with open(manifest, "rb") as fh:
                declared = {t.get("NSPrivacyAccessedAPIType") for t in
                            plistlib.load(fh).get("NSPrivacyAccessedAPITypes", [])}
        else:
            warn("manifest not found")
        used = {}
        for src in sources(dirs):
            body = strip_comments(src.read_text(errors="ignore"))
            for cat, pats in REASON_APIS.items():
                for pat in pats:
                    for m in re.finditer(pat, body):
                        line = body.count("\n", 0, m.start()) + 1
                        used.setdefault(cat, []).append(f"{src}:{line} {m.group(0)}")
        for cat in sorted(set(used) | declared):
            short = cat.replace("NSPrivacyAccessedAPICategory", "")
            if cat in used and cat not in declared:
                fail(f"{short} used but not declared — e.g. {used[cat][0]}" +
                     (f" (+{len(used[cat]) - 1} more)" if len(used[cat]) > 1 else ""))
            elif cat in used:
                ok(f"{short} used and declared ({len(used[cat])} sites)")
            else:
                warn(f"{short} declared but no use found in these dirs (a dependency may need it; else remove)")
        if not used and not declared:
            ok("no required-reason APIs found or declared")
        print("    (a pattern hit is a lead, not proof: check each site, and pick the reason code that fits)")


# ---------------------------------------------------------------- network

def cmd_network(args):
    print("[network code]")
    total = 0
    for src in sources(args.dirs):
        body = strip_comments(src.read_text(errors="ignore"))
        for pat in NETWORK_PATTERNS:
            for m in re.finditer(pat, body, re.M):
                total += 1
                line = body.count("\n", 0, m.start()) + 1
                print(f"  {src}:{line} {m.group(0).strip()}")
    print(f"  {total} site(s). Check each against the privacy label, the privacy policy and the listing's claims.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("archive")
    a.add_argument("archive")
    a.add_argument("--expect-version")
    a.add_argument("--expect-build")
    a.add_argument("--debug-marker", action="append")
    r = sub.add_parser("reasons")
    r.add_argument("--target", nargs="+", action="append", required=True,
                   metavar="NAME MANIFEST DIR", help="target name, its PrivacyInfo.xcprivacy, then its source dirs")
    n = sub.add_parser("network")
    n.add_argument("dirs", nargs="+")
    args = p.parse_args()
    if args.command == "reasons" and any(len(t) < 3 for t in args.target):
        p.error("--target needs NAME MANIFEST and at least one DIR")
    {"archive": cmd_archive, "reasons": cmd_reasons, "network": cmd_network}[args.command](args)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
