#!/usr/bin/env bash
# Capture App Store screenshot raws from the simulator through the app's
# DEBUG router (`-ios-genesis-screen <Name>`). Template: copy into the target
# repo (docs/appstore-screenshots/capture.sh) and adjust the routes file.
#
#   capture.sh --udid <UDID> --bundle-id <id> --app <path/to/Debug-iphonesimulator/App.app> \
#              --routes routes.txt --out docs/appstore-screenshots/raw/v1/en-US \
#              [--locale es-MX] [--display primary|primary-1] [--grant motion,photos] [--wait 2]
#
# routes.txt: one raw per line, `<RawName> <Route> [extra launch args...]`, e.g.
#   Home        Home
#   History     HistoryPopulated -historySeed mixed
#   Welcome     Welcome
# A line's extra args are passed to `simctl launch` after the route.
#
# (Array expansions use ${a[@]+...} so empty arrays work under macOS bash 3.2 with set -u.)
#
# Read-only for the project: it installs a DEBUG build on a simulator and
# writes PNGs under --out. Raws come from a DEBUG build; the Release audit
# (release_audit.py archive) separately proves the routes aren't in Release.
set -euo pipefail

UDID="" BID="" APP="" ROUTES="" OUT="" LOCALE="" DISPLAY="" GRANT="" WAIT=2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --udid) UDID="$2"; shift 2 ;;
    --bundle-id) BID="$2"; shift 2 ;;
    --app) APP="$2"; shift 2 ;;
    --routes) ROUTES="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --locale) LOCALE="$2"; shift 2 ;;
    --display) DISPLAY="$2"; shift 2 ;;
    --grant) GRANT="$2"; shift 2 ;;
    --wait) WAIT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$UDID" && -n "$BID" && -n "$ROUTES" && -n "$OUT" ]] || {
  echo "need --udid, --bundle-id, --routes and --out" >&2; exit 2; }
mkdir -p "$OUT"

xcrun simctl bootstatus "$UDID" -b >/dev/null
# 9:41, full battery and signal: the composer crops the status bar off anyway,
# but a consistent bar keeps uncropped raws (creatives, Duo) clean.
xcrun simctl status_bar "$UDID" override --time "9:41" --batteryState charged \
  --batteryLevel 100 --cellularBars 4 --wifiBars 3 >/dev/null
[[ -n "$APP" ]] && xcrun simctl install "$UDID" "$APP"
# Pre-grant permissions so a system prompt doesn't float over the next capture.
IFS=',' read -ra PERMS <<< "$GRANT"
for perm in ${PERMS[@]+"${PERMS[@]}"}; do
  [[ -n "$perm" ]] && xcrun simctl privacy "$UDID" grant "$perm" "$BID" || true
done

LOCALE_ARGS=()
if [[ -n "$LOCALE" ]]; then
  LOCALE_ARGS=(-AppleLanguages "(${LOCALE})" -AppleLocale "${LOCALE/-/_}")
fi
DISPLAY_ARGS=()
[[ -n "$DISPLAY" ]] && DISPLAY_ARGS=(--display="$DISPLAY")

while read -r name route extra; do
  [[ -z "${name:-}" || "$name" == \#* ]] && continue
  xcrun simctl terminate "$UDID" "$BID" </dev/null >/dev/null 2>&1 || true
  # shellcheck disable=SC2086
  xcrun simctl launch "$UDID" "$BID" -ios-genesis-screen "$route" ${LOCALE_ARGS[@]+"${LOCALE_ARGS[@]}"} $extra </dev/null >/dev/null
  sleep "$WAIT"
  xcrun simctl io "$UDID" screenshot ${DISPLAY_ARGS[@]+"${DISPLAY_ARGS[@]}"} "$OUT/$name.png" </dev/null >/dev/null
  echo "  $OUT/$name.png ← $route${extra:+ $extra}"
done < "$ROUTES"   # simctl calls above read </dev/null so they never eat the routes file

xcrun simctl status_bar "$UDID" clear >/dev/null || true
