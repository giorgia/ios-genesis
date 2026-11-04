#!/usr/bin/env python3
"""Keyword rank and competition from Apple's public iTunes Search API.

Read-only, no credentials. For each term: where the app ranks in the top
`--limit` results, and "competition" = the median rating count of the top 10
apps (lower is easier to rank on). Apple doesn't publish search volume, so
popularity isn't measured here; check Keyword popularity in Apple Search Ads.

The Search API's order is a close proxy for App Store search, not App Store
Connect data. Run the same terms with the same storefront at every checkpoint
(baseline, day 14, day 28) so the comparison is like for like.

  aso_rank.py --app-id 1234567890 --country us "rep counter" "jump rope counter"
  aso_rank.py --app-id 1234567890 --terms-file docs/aso-terms.txt --markdown
"""
import argparse
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request

SEARCH = "https://itunes.apple.com/search"
# The Search API allows roughly 20 calls a minute.
PAUSE_SECONDS = 3.2


def search(term, country, limit):
    q = urllib.parse.urlencode({"term": term, "entity": "software", "country": country, "limit": limit})
    with urllib.request.urlopen(f"{SEARCH}?{q}", timeout=30) as resp:
        return json.load(resp).get("results", [])


def lookup(app_id, country):
    q = urllib.parse.urlencode({"id": app_id, "country": country})
    with urllib.request.urlopen(f"https://itunes.apple.com/lookup?{q}", timeout=30) as resp:
        results = json.load(resp).get("results", [])
    return results[0] if results else None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("terms", nargs="*")
    p.add_argument("--app-id", required=True, help="the App Store app id (trackId)")
    p.add_argument("--country", default="us")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--terms-file", help="one term per line")
    p.add_argument("--markdown", action="store_true", help="print a markdown table")
    args = p.parse_args()
    terms = list(args.terms)
    if args.terms_file:
        terms += [l.strip() for l in open(args.terms_file) if l.strip() and not l.startswith("#")]
    if not terms:
        sys.exit("No terms given.")

    app = lookup(args.app_id, args.country)
    if app:
        print(f"{app.get('trackName')} {app.get('version')} — released {app.get('currentVersionReleaseDate', '?')[:10]}, "
              f"{app.get('userRatingCount', 0)} ratings ({args.country.upper()} storefront)\n")
    rows = []
    for i, term in enumerate(terms):
        if i:
            time.sleep(PAUSE_SECONDS)
        results = search(term, args.country, args.limit)
        rank = next((n for n, r in enumerate(results, 1) if str(r.get("trackId")) == str(args.app_id)), None)
        top = results[:10]
        competition = int(statistics.median([r.get("userRatingCount", 0) for r in top])) if top else 0
        leaders = ", ".join(f"{r.get('trackName', '?')[:28]} ({r.get('userRatingCount', 0)})" for r in top[:3])
        rows.append((term, rank, len(results), competition, leaders))

    if args.markdown:
        print("| Term | Rank | Competition (median ratings, top 10) | Top 3 |")
        print("|---|---|---|---|")
        for term, rank, n, comp, leaders in rows:
            print(f"| {term} | {rank if rank else f'not in top {n}'} | {comp:,} | {leaders} |")
    else:
        for term, rank, n, comp, leaders in rows:
            print(f"{term:32} rank {str(rank) if rank else f'>{n}':>6}   competition {comp:>8,}   {leaders}")


if __name__ == "__main__":
    main()
